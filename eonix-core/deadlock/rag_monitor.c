/*
 * Eonix OS — Self-Healing Deadlock Manager (Full Implementation)
 * ==============================================================
 * Linux kernel module that maintains a Resource Allocation Graph (RAG),
 * runs iterative DFS cycle detection every 500ms, and automatically
 * recovers from deadlocks by terminating the lowest-priority process.
 *
 * Features:
 *   - RAG with process and resource node tracking
 *   - kprobes on do_exit / __mutex_lock_slowpath / mutex_unlock
 *   - Iterative DFS cycle detection (no recursion — safe for kernel stack)
 *   - Automatic recovery via SIGTERM then SIGKILL
 *   - /proc/eonix/deadlock_log   — event log
 *   - /proc/eonix/rag_state      — live RAG dump
 *   - /proc/eonix/rag_inject     — test harness for userspace
 *   - hrtimer-based periodic monitoring
 *
 * Build: make
 * Load:  sudo insmod eonix_deadlock.ko
 * Check: cat /proc/eonix/deadlock_log
 *        cat /proc/eonix/rag_state
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#include <linux/hrtimer.h>
#include <linux/ktime.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/rwlock.h>
#include <linux/kprobes.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/signal.h>
#include <linux/uaccess.h>
#include <linux/string.h>
#include <linux/delay.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("shahnoor-exe");
MODULE_DESCRIPTION("Eonix OS Self-Healing Deadlock Manager");
MODULE_VERSION("0.2.0");

/* ---- Configuration ---- */
#define MAX_PROCESSES           256
#define MAX_RESOURCES           128
#define MAX_WAITERS             16
#define MAX_HELD                16
#define DETECTION_INTERVAL_MS   500
#define LOG_BUFFER_SIZE         8192
#define RECOVERY_TIMEOUT_MS     200
#define MAX_CYCLE_LEN           MAX_PROCESSES

/* ===== PART 1 — Data Structures ===== */

struct rag_resource {
	int       resource_id;
	pid_t     held_by;              /* 0 = free */
	pid_t     waited_by[MAX_WAITERS];
	int       waiter_count;
	spinlock_t lock;
};

struct rag_process {
	pid_t     pid;
	char      comm[TASK_COMM_LEN];
	int       held_resources[MAX_HELD];
	int       held_count;
	int       waiting_for;          /* resource_id, -1 = not waiting */
	int       priority_score;       /* lower = evict first */
	bool      active;
};

/* Global arrays */
static struct rag_resource resources[MAX_RESOURCES];
static struct rag_process  processes[MAX_PROCESSES];
static DEFINE_RWLOCK(rag_lock);

/* Logging */
static char   log_buffer[LOG_BUFFER_SIZE];
static int    log_offset;
static DEFINE_SPINLOCK(log_lock);

/* Statistics */
static unsigned long deadlock_count;
static unsigned long recovery_count;

/* Timer */
static struct hrtimer detection_timer;

/* /proc directory */
static struct proc_dir_entry *eonix_proc_dir;

/* kprobes */
static struct kprobe kp_do_exit;
static struct kprobe kp_mutex_lock_slow;
static struct kprobe kp_mutex_unlock;
static bool kprobes_registered;

/* ---- Helpers ---- */

static void rag_log(const char *fmt, ...)
{
	va_list args;
	unsigned long flags;
	int written;
	u64 ts_ms;

	ts_ms = ktime_to_ms(ktime_get_boottime());

	spin_lock_irqsave(&log_lock, flags);
	if (log_offset < LOG_BUFFER_SIZE - 128) {
		written = scnprintf(log_buffer + log_offset,
				    LOG_BUFFER_SIZE - log_offset,
				    "[%llu] ", ts_ms);
		log_offset += written;

		va_start(args, fmt);
		written = vscnprintf(log_buffer + log_offset,
				     LOG_BUFFER_SIZE - log_offset,
				     fmt, args);
		va_end(args);
		log_offset += written;

		if (log_offset < LOG_BUFFER_SIZE - 1)
			log_buffer[log_offset++] = '\n';
	}
	spin_unlock_irqrestore(&log_lock, flags);
}

static int find_process(pid_t pid)
{
	int i;

	for (i = 0; i < MAX_PROCESSES; i++) {
		if (processes[i].active && processes[i].pid == pid)
			return i;
	}
	return -1;
}

static int find_or_create_process(pid_t pid)
{
	int i, slot = -1;

	for (i = 0; i < MAX_PROCESSES; i++) {
		if (processes[i].active && processes[i].pid == pid)
			return i;
		if (!processes[i].active && slot < 0)
			slot = i;
	}
	if (slot >= 0) {
		processes[slot].pid = pid;
		processes[slot].active = true;
		processes[slot].held_count = 0;
		processes[slot].waiting_for = -1;
		processes[slot].priority_score = 50;
		memset(processes[slot].held_resources, -1,
		       sizeof(processes[slot].held_resources));
		if (current->pid == pid)
			get_task_comm(processes[slot].comm, current);
		else
			scnprintf(processes[slot].comm, TASK_COMM_LEN,
				  "pid-%d", pid);
	}
	return slot;
}

static int find_or_create_resource(int resource_id)
{
	if (resource_id < 0 || resource_id >= MAX_RESOURCES)
		return -1;
	/* Direct-mapped: slot = resource_id */
	resources[resource_id].resource_id = resource_id;
	return resource_id;
}

/* ===== PART 2 — kprobe Handlers ===== */

/* do_exit(): release all resources when a process exits */
static int handler_do_exit(struct kprobe *p, struct pt_regs *regs)
{
	pid_t pid = current->pid;
	int idx, i, rid;
	unsigned long flags;

	write_lock_irqsave(&rag_lock, flags);
	idx = find_process(pid);
	if (idx >= 0) {
		for (i = 0; i < processes[idx].held_count; i++) {
			rid = processes[idx].held_resources[i];
			if (rid >= 0 && rid < MAX_RESOURCES)
				resources[rid].held_by = 0;
		}
		processes[idx].active = false;
		processes[idx].held_count = 0;
		processes[idx].waiting_for = -1;
	}
	write_unlock_irqrestore(&rag_lock, flags);
	return 0;
}

/* __mutex_lock_slowpath(): process is contending on a kernel mutex */
static int handler_mutex_lock_slow(struct kprobe *p, struct pt_regs *regs)
{
	pid_t pid = current->pid;
	int idx;
	unsigned long flags;
	int resource_id;

#ifdef CONFIG_X86_64
	resource_id = (int)(regs->di & 0x7F);
#else
	resource_id = (int)(pid & 0x7F);
#endif

	write_lock_irqsave(&rag_lock, flags);
	idx = find_or_create_process(pid);
	if (idx >= 0) {
		processes[idx].waiting_for = resource_id;
		find_or_create_resource(resource_id);
		if (resources[resource_id].waiter_count < MAX_WAITERS)
			resources[resource_id].waited_by[
				resources[resource_id].waiter_count++] = pid;
	}
	write_unlock_irqrestore(&rag_lock, flags);
	return 0;
}

/* mutex_unlock(): process released a kernel mutex */
static int handler_mutex_unlock(struct kprobe *p, struct pt_regs *regs)
{
	pid_t pid = current->pid;
	int idx, i;
	unsigned long flags;
	int resource_id;

#ifdef CONFIG_X86_64
	resource_id = (int)(regs->di & 0x7F);
#else
	resource_id = (int)(pid & 0x7F);
#endif

	write_lock_irqsave(&rag_lock, flags);
	idx = find_process(pid);
	if (idx >= 0 && resource_id >= 0 && resource_id < MAX_RESOURCES) {
		resources[resource_id].held_by = 0;
		for (i = 0; i < processes[idx].held_count; i++) {
			if (processes[idx].held_resources[i] == resource_id) {
				processes[idx].held_resources[i] =
					processes[idx].held_resources[
						--processes[idx].held_count];
				break;
			}
		}
	}
	write_unlock_irqrestore(&rag_lock, flags);
	return 0;
}

/* ===== PART 3 — Iterative DFS Cycle Detection ===== */

/*
 * Build adjacency: process A → process B when A waits for a resource held by B.
 * Returns 1 if cycle found; fills cycle_pids/cycle_len and selects a victim.
 */
static int rag_detect_cycle(pid_t *victim_pid, pid_t *cycle_pids, int *cycle_len)
{
	int adj[MAX_PROCESSES];
	u8 visited[MAX_PROCESSES];
	u8 in_path[MAX_PROCESSES];
	int i, cur, rid, holder_idx;
	int best_victim_idx, best_score;

	*cycle_len = 0;
	*victim_pid = 0;

	memset(adj, -1, sizeof(adj));
	for (i = 0; i < MAX_PROCESSES; i++) {
		if (!processes[i].active || processes[i].waiting_for < 0)
			continue;
		rid = processes[i].waiting_for;
		if (rid < 0 || rid >= MAX_RESOURCES)
			continue;
		if (resources[rid].held_by == 0)
			continue;
		holder_idx = find_process(resources[rid].held_by);
		if (holder_idx >= 0 && holder_idx != i)
			adj[i] = holder_idx;
	}

	memset(visited, 0, sizeof(visited));
	memset(in_path, 0, sizeof(in_path));

	for (i = 0; i < MAX_PROCESSES; i++) {
		if (!processes[i].active || visited[i])
			continue;

		/* Walk the chain */
		cur = i;
		while (cur >= 0 && !visited[cur] && !in_path[cur]) {
			in_path[cur] = 1;
			cur = adj[cur];
		}

		/* Cycle found if we hit a node already in current path */
		if (cur >= 0 && in_path[cur]) {
			int start = cur;
			int c = cur;

			*cycle_len = 0;
			do {
				if (*cycle_len < MAX_CYCLE_LEN)
					cycle_pids[(*cycle_len)++] = processes[c].pid;
				c = adj[c];
			} while (c != start && c >= 0 && *cycle_len < MAX_CYCLE_LEN);

			/* Select victim: lowest priority_score in cycle */
			best_victim_idx = start;
			best_score = processes[start].priority_score;
			c = start;
			do {
				if (processes[c].priority_score < best_score) {
					best_score = processes[c].priority_score;
					best_victim_idx = c;
				}
				c = adj[c];
			} while (c != start && c >= 0);

			*victim_pid = processes[best_victim_idx].pid;

			/* Clean up in_path */
			c = i;
			while (c >= 0 && in_path[c]) {
				visited[c] = 1;
				in_path[c] = 0;
				c = adj[c];
			}
			return 1;
		}

		/* No cycle — mark entire chain visited */
		cur = i;
		while (cur >= 0 && in_path[cur]) {
			visited[cur] = 1;
			in_path[cur] = 0;
			cur = adj[cur];
		}
	}
	return 0;
}

/* ===== PART 4 — Recovery Engine ===== */

static void rag_recover(pid_t victim_pid, pid_t *cycle_pids, int cycle_len)
{
	struct task_struct *victim_task;
	int idx, i, j, rid;
	u64 start_time, end_time;
	char cycle_str[256];
	int coff = 0;

	start_time = ktime_to_ms(ktime_get_boottime());

	for (i = 0; i < cycle_len && coff < 240; i++)
		coff += scnprintf(cycle_str + coff, 256 - coff,
				  "%s%d", i ? "," : "", cycle_pids[i]);

	pr_warn("EONIX_RAG: DEADLOCK DETECTED — cycle: [%s]\n", cycle_str);
	rag_log("DEADLOCK_DETECTED pids=[%s]", cycle_str);

	/* Release victim's resources */
	idx = find_process(victim_pid);
	if (idx >= 0) {
		pr_info("EONIX_RAG: Victim PID=%d (%s) prio=%d\n",
			victim_pid, processes[idx].comm,
			processes[idx].priority_score);

		for (i = 0; i < processes[idx].held_count; i++) {
			rid = processes[idx].held_resources[i];
			if (rid >= 0 && rid < MAX_RESOURCES) {
				resources[rid].held_by = 0;
				for (j = 0; j < resources[rid].waiter_count; j++) {
					int widx = find_process(
						resources[rid].waited_by[j]);
					if (widx >= 0)
						processes[widx].waiting_for = -1;
				}
				resources[rid].waiter_count = 0;
			}
		}
		processes[idx].held_count = 0;
		processes[idx].waiting_for = -1;
	}

	/* Send SIGTERM, wait, then SIGKILL if still alive */
	rcu_read_lock();
	victim_task = pid_task(find_vpid(victim_pid), PIDTYPE_PID);
	if (victim_task) {
		get_task_struct(victim_task);
		rcu_read_unlock();

		send_sig(SIGTERM, victim_task, 1);
		pr_info("EONIX_RAG: Sent SIGTERM to PID %d\n", victim_pid);

		msleep(RECOVERY_TIMEOUT_MS);

		if (pid_alive(victim_task)) {
			send_sig(SIGKILL, victim_task, 1);
			pr_info("EONIX_RAG: Sent SIGKILL to PID %d\n",
				victim_pid);
		}
		put_task_struct(victim_task);
	} else {
		rcu_read_unlock();
	}

	if (idx >= 0)
		processes[idx].active = false;

	end_time = ktime_to_ms(ktime_get_boottime());
	pr_info("EONIX_RAG: Deadlock resolved — victim=%d latency=%llums\n",
		victim_pid, end_time - start_time);
	rag_log("RECOVERY_COMPLETE victim=%d duration_ms=%llu",
		victim_pid, end_time - start_time);

	deadlock_count++;
	recovery_count++;
}

/* ===== PART 5 — Timer-Based Monitor ===== */

static enum hrtimer_restart detection_timer_fn(struct hrtimer *timer)
{
	pid_t victim_pid = 0;
	pid_t cycle_pids[MAX_CYCLE_LEN];
	int cycle_len = 0;
	unsigned long flags;

	read_lock_irqsave(&rag_lock, flags);
	if (rag_detect_cycle(&victim_pid, cycle_pids, &cycle_len)) {
		read_unlock_irqrestore(&rag_lock, flags);
		write_lock_irqsave(&rag_lock, flags);
		rag_recover(victim_pid, cycle_pids, cycle_len);
		write_unlock_irqrestore(&rag_lock, flags);
	} else {
		read_unlock_irqrestore(&rag_lock, flags);
	}

	hrtimer_forward_now(timer, ms_to_ktime(DETECTION_INTERVAL_MS));
	return HRTIMER_RESTART;
}

/* ===== PART 6 — /proc Interface ===== */

/* /proc/eonix/deadlock_log */
static int deadlock_log_show(struct seq_file *m, void *v)
{
	unsigned long flags;
	int i, active = 0;

	spin_lock_irqsave(&log_lock, flags);
	if (log_offset > 0)
		seq_printf(m, "%s", log_buffer);
	else
		seq_puts(m, "[EONIX] No deadlocks detected\n");
	spin_unlock_irqrestore(&log_lock, flags);

	read_lock_irqsave(&rag_lock, flags);
	for (i = 0; i < MAX_PROCESSES; i++)
		if (processes[i].active)
			active++;
	read_unlock_irqrestore(&rag_lock, flags);

	seq_printf(m, "[status] deadlocks=%lu recoveries=%lu active=%d\n",
		   deadlock_count, recovery_count, active);
	return 0;
}

static int deadlock_log_open(struct inode *inode, struct file *file)
{
	return single_open(file, deadlock_log_show, NULL);
}

static const struct proc_ops deadlock_log_ops = {
	.proc_open    = deadlock_log_open,
	.proc_read    = seq_read,
	.proc_lseek   = seq_lseek,
	.proc_release = single_release,
};

/* /proc/eonix/rag_state */
static int rag_state_show(struct seq_file *m, void *v)
{
	unsigned long flags;
	int i, j;

	read_lock_irqsave(&rag_lock, flags);

	seq_puts(m, "=== Eonix RAG State ===\n\n");
	seq_puts(m, "--- Processes ---\n");
	for (i = 0; i < MAX_PROCESSES; i++) {
		if (!processes[i].active)
			continue;
		seq_printf(m, "PROCESS pid=%d name=%s holds=[",
			   processes[i].pid, processes[i].comm);
		for (j = 0; j < processes[i].held_count; j++)
			seq_printf(m, "%s%d", j ? "," : "",
				   processes[i].held_resources[j]);
		seq_printf(m, "] waiting_for=%d priority=%d\n",
			   processes[i].waiting_for,
			   processes[i].priority_score);
	}

	seq_puts(m, "\n--- Resources ---\n");
	for (i = 0; i < MAX_RESOURCES; i++) {
		if (resources[i].held_by == 0 && resources[i].waiter_count == 0)
			continue;
		seq_printf(m, "RESOURCE id=%d held_by=%d waiters=[",
			   resources[i].resource_id, resources[i].held_by);
		for (j = 0; j < resources[i].waiter_count; j++)
			seq_printf(m, "%s%d", j ? "," : "",
				   resources[i].waited_by[j]);
		seq_puts(m, "]\n");
	}

	seq_printf(m, "\n[stats] deadlocks=%lu recoveries=%lu\n",
		   deadlock_count, recovery_count);
	read_unlock_irqrestore(&rag_lock, flags);
	return 0;
}

static int rag_state_open(struct inode *inode, struct file *file)
{
	return single_open(file, rag_state_show, NULL);
}

static const struct proc_ops rag_state_ops = {
	.proc_open    = rag_state_open,
	.proc_read    = seq_read,
	.proc_lseek   = seq_lseek,
	.proc_release = single_release,
};

/*
 * /proc/eonix/rag_inject — test harness for userspace.
 *
 * Commands (write one per line):
 *   HOLD <pid> <resource_id>      — pid acquires resource
 *   WAIT <pid> <resource_id>      — pid waits for resource
 *   RELEASE <pid> <resource_id>   — pid releases resource
 *   RESET                         — clear all state
 *   PRIORITY <pid> <score>        — set priority score
 */
static ssize_t rag_inject_write(struct file *file, const char __user *ubuf,
				size_t count, loff_t *ppos)
{
	char buf[128];
	int pid_val, res_id, score;
	int idx, ridx;
	unsigned long flags;
	size_t len;

	len = min(count, sizeof(buf) - 1);
	if (copy_from_user(buf, ubuf, len))
		return -EFAULT;
	buf[len] = '\0';

	if (len > 0 && buf[len - 1] == '\n')
		buf[--len] = '\0';

	write_lock_irqsave(&rag_lock, flags);

	if (sscanf(buf, "HOLD %d %d", &pid_val, &res_id) == 2) {
		idx = find_or_create_process((pid_t)pid_val);
		ridx = find_or_create_resource(res_id);
		if (idx >= 0 && ridx >= 0) {
			resources[ridx].held_by = (pid_t)pid_val;
			if (processes[idx].held_count < MAX_HELD)
				processes[idx].held_resources[
					processes[idx].held_count++] = res_id;
			if (processes[idx].waiting_for == res_id)
				processes[idx].waiting_for = -1;
		}
	} else if (sscanf(buf, "WAIT %d %d", &pid_val, &res_id) == 2) {
		idx = find_or_create_process((pid_t)pid_val);
		ridx = find_or_create_resource(res_id);
		if (idx >= 0 && ridx >= 0) {
			processes[idx].waiting_for = res_id;
			if (resources[ridx].waiter_count < MAX_WAITERS)
				resources[ridx].waited_by[
					resources[ridx].waiter_count++] =
					(pid_t)pid_val;
		}
	} else if (sscanf(buf, "RELEASE %d %d", &pid_val, &res_id) == 2) {
		idx = find_process((pid_t)pid_val);
		if (idx >= 0 && res_id >= 0 && res_id < MAX_RESOURCES) {
			int k;

			resources[res_id].held_by = 0;
			for (k = 0; k < processes[idx].held_count; k++) {
				if (processes[idx].held_resources[k] == res_id) {
					processes[idx].held_resources[k] =
						processes[idx].held_resources[
							--processes[idx].held_count];
					break;
				}
			}
		}
	} else if (sscanf(buf, "PRIORITY %d %d", &pid_val, &score) == 2) {
		idx = find_process((pid_t)pid_val);
		if (idx >= 0)
			processes[idx].priority_score = score;
	} else if (strncmp(buf, "RESET", 5) == 0) {
		memset(processes, 0, sizeof(processes));
		memset(resources, 0, sizeof(resources));
		deadlock_count = 0;
		recovery_count = 0;
		spin_lock(&log_lock);
		log_offset = 0;
		spin_unlock(&log_lock);
		pr_info("EONIX_RAG: State reset via rag_inject\n");
	}

	write_unlock_irqrestore(&rag_lock, flags);
	return count;
}

static int rag_inject_show(struct seq_file *m, void *v)
{
	seq_puts(m, "Eonix RAG Inject Interface\n");
	seq_puts(m, "Commands: HOLD|WAIT|RELEASE <pid> <rid>, ");
	seq_puts(m, "PRIORITY <pid> <score>, RESET\n");
	return 0;
}

static int rag_inject_open(struct inode *inode, struct file *file)
{
	return single_open(file, rag_inject_show, NULL);
}

static const struct proc_ops rag_inject_ops = {
	.proc_open    = rag_inject_open,
	.proc_read    = seq_read,
	.proc_write   = rag_inject_write,
	.proc_lseek   = seq_lseek,
	.proc_release = single_release,
};

/* ===== PART 2 setup — kprobe registration ===== */

static int register_kprobes_safe(void)
{
	int ret;

	memset(&kp_do_exit, 0, sizeof(kp_do_exit));
	kp_do_exit.symbol_name = "do_exit";
	kp_do_exit.pre_handler = handler_do_exit;

	memset(&kp_mutex_lock_slow, 0, sizeof(kp_mutex_lock_slow));
	kp_mutex_lock_slow.symbol_name = "__mutex_lock_slowpath";
	kp_mutex_lock_slow.pre_handler = handler_mutex_lock_slow;

	memset(&kp_mutex_unlock, 0, sizeof(kp_mutex_unlock));
	kp_mutex_unlock.symbol_name = "mutex_unlock";
	kp_mutex_unlock.pre_handler = handler_mutex_unlock;

	ret = register_kprobe(&kp_do_exit);
	if (ret < 0) {
		pr_warn("EONIX_RAG: kprobe do_exit failed (%d)\n", ret);
		return ret;
	}

	ret = register_kprobe(&kp_mutex_lock_slow);
	if (ret < 0) {
		pr_warn("EONIX_RAG: kprobe __mutex_lock_slowpath failed (%d)\n", ret);
		unregister_kprobe(&kp_do_exit);
		return ret;
	}

	ret = register_kprobe(&kp_mutex_unlock);
	if (ret < 0) {
		pr_warn("EONIX_RAG: kprobe mutex_unlock failed (%d)\n", ret);
		unregister_kprobe(&kp_do_exit);
		unregister_kprobe(&kp_mutex_lock_slow);
		return ret;
	}

	kprobes_registered = true;
	pr_info("EONIX_RAG: kprobes registered (do_exit, __mutex_lock_slowpath, mutex_unlock)\n");
	return 0;
}

static void unregister_kprobes_safe(void)
{
	if (!kprobes_registered)
		return;
	unregister_kprobe(&kp_do_exit);
	unregister_kprobe(&kp_mutex_lock_slow);
	unregister_kprobe(&kp_mutex_unlock);
	kprobes_registered = false;
}

/* ===== PART 7 — Module Init / Exit ===== */

static int __init eonix_deadlock_init(void)
{
	int i;

	pr_info("EONIX_RAG: Monitor v0.2.0 loading\n");

	/* Initialize data structures */
	memset(processes, 0, sizeof(processes));
	memset(resources, 0, sizeof(resources));
	for (i = 0; i < MAX_RESOURCES; i++) {
		resources[i].resource_id = i;
		spin_lock_init(&resources[i].lock);
	}
	log_offset = 0;
	deadlock_count = 0;
	recovery_count = 0;

	/* Register kprobes (non-fatal if they fail) */
	register_kprobes_safe();

	/* Start hrtimer */
	hrtimer_init(&detection_timer, CLOCK_MONOTONIC, HRTIMER_MODE_REL);
	detection_timer.function = detection_timer_fn;
	hrtimer_start(&detection_timer, ms_to_ktime(DETECTION_INTERVAL_MS),
		      HRTIMER_MODE_REL);
	pr_info("EONIX_RAG: hrtimer started (%dms interval)\n",
		DETECTION_INTERVAL_MS);

	/* Create /proc/eonix/ */
	eonix_proc_dir = proc_mkdir("eonix", NULL);
	if (!eonix_proc_dir) {
		pr_err("EONIX_RAG: Failed to create /proc/eonix\n");
		hrtimer_cancel(&detection_timer);
		unregister_kprobes_safe();
		return -ENOMEM;
	}
	proc_create("deadlock_log", 0444, eonix_proc_dir, &deadlock_log_ops);
	proc_create("rag_state", 0444, eonix_proc_dir, &rag_state_ops);
	proc_create("rag_inject", 0666, eonix_proc_dir, &rag_inject_ops);

	pr_info("EONIX_RAG: /proc/eonix/{deadlock_log,rag_state,rag_inject} created\n");
	pr_info("EONIX_RAG: Monitor loaded — detection active\n");

	return 0;
}

static void __exit eonix_deadlock_exit(void)
{
	hrtimer_cancel(&detection_timer);
	unregister_kprobes_safe();
	remove_proc_subtree("eonix", NULL);
	pr_info("EONIX_RAG: Monitor unloaded (deadlocks=%lu recoveries=%lu)\n",
		deadlock_count, recovery_count);
}

module_init(eonix_deadlock_init);
module_exit(eonix_deadlock_exit);
