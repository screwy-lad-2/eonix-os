/*
 * Eonix OS — Process Checkpoint Manager
 * ======================================
 * Before killing a deadlocked process, saves its key state so it can be
 * restarted cleanly.  Provides /proc/eonix/checkpoints for inspection.
 *
 * This file is compiled into the eonix_deadlock.ko module together with
 * rag_monitor.c.
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/cred.h>
#include <linux/fs.h>
#include <linux/fs_struct.h>
#include <linux/mm.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#include <linux/string.h>
#include <linux/ktime.h>

#include "checkpoint.h"

/* ===== Storage ===== */

static struct eonix_checkpoint checkpoints[MAX_CHECKPOINTS];
static int checkpoint_head;
static DEFINE_SPINLOCK(checkpoint_lock);

/* ===== PART 2 — Checkpoint Functions ===== */

int eonix_checkpoint_save(pid_t pid, const int *held, int held_count,
			  int waiting_for)
{
	struct eonix_checkpoint *ck;
	struct task_struct *task;
	unsigned long flags;
	int slot, i;

	rcu_read_lock();
	task = pid_task(find_vpid(pid), PIDTYPE_PID);
	if (!task) {
		rcu_read_unlock();
		/* Process may already have been reaped — store what we know */
		spin_lock_irqsave(&checkpoint_lock, flags);
		slot = checkpoint_head % MAX_CHECKPOINTS;
		ck = &checkpoints[slot];

		ck->magic        = CHECKPOINT_MAGIC;
		ck->pid          = pid;
		scnprintf(ck->comm, sizeof(ck->comm), "pid-%d", pid);
		ck->timestamp_ns = ktime_get_real_ns();
		ck->exit_code    = -1;
		ck->held_count   = 0;
		ck->waiting_for  = waiting_for;
		ck->uid          = 0;
		ck->gid          = 0;
		ck->exe_path[0]  = '\0';
		ck->cmdline[0]   = '\0';
		ck->valid        = true;

		for (i = 0; i < held_count && i < 16; i++)
			ck->held_resources[i] = held[i];
		ck->held_count = min(held_count, 16);

		checkpoint_head++;
		spin_unlock_irqrestore(&checkpoint_lock, flags);

		pr_info("EONIX_CKPT: Saved checkpoint for PID=%d name=%s exe=(unknown)\n",
			pid, ck->comm);
		return slot;
	}

	get_task_struct(task);
	rcu_read_unlock();

	spin_lock_irqsave(&checkpoint_lock, flags);
	slot = checkpoint_head % MAX_CHECKPOINTS;
	ck = &checkpoints[slot];

	ck->magic        = CHECKPOINT_MAGIC;
	ck->pid          = pid;
	get_task_comm(ck->comm, task);
	ck->timestamp_ns = ktime_get_real_ns();
	ck->exit_code    = -1;
	ck->uid          = __kuid_val(task_uid(task));
	ck->gid          = __kgid_val(__task_cred(task)->gid);
	ck->waiting_for  = waiting_for;
	ck->valid        = true;

	/* Copy held resources from caller data (RAG state) */
	for (i = 0; i < held_count && i < 16; i++)
		ck->held_resources[i] = held[i];
	ck->held_count = min(held_count, 16);

	/* Resolve executable path via task->mm->exe_file under rcu */
	ck->exe_path[0] = '\0';
	if (task->mm) {
		struct file *ef;

		rcu_read_lock();
		ef = rcu_dereference(task->mm->exe_file);
		if (ef) {
			char *pathbuf = kmalloc(256, GFP_ATOMIC);
			if (pathbuf) {
				char *p = d_path(&ef->f_path, pathbuf, 256);
				if (!IS_ERR(p))
					strscpy(ck->exe_path, p,
						sizeof(ck->exe_path));
				kfree(pathbuf);
			}
		}
		rcu_read_unlock();
	}

	/* Command line from task->comm as a fallback (kernel can't easily
	 * read /proc/pid/cmdline from module context) */
	scnprintf(ck->cmdline, sizeof(ck->cmdline), "%s", ck->comm);

	checkpoint_head++;
	spin_unlock_irqrestore(&checkpoint_lock, flags);

	put_task_struct(task);

	pr_info("EONIX_CKPT: Saved checkpoint for PID=%d name=%s exe=%s\n",
		pid, ck->comm,
		ck->exe_path[0] ? ck->exe_path : "(unknown)");
	return slot;
}
EXPORT_SYMBOL_GPL(eonix_checkpoint_save);

struct eonix_checkpoint *eonix_checkpoint_get(pid_t pid)
{
	int i, newest_idx = -1;
	u64 newest_ts = 0;
	unsigned long flags;

	spin_lock_irqsave(&checkpoint_lock, flags);
	for (i = 0; i < MAX_CHECKPOINTS; i++) {
		if (checkpoints[i].valid &&
		    checkpoints[i].magic == CHECKPOINT_MAGIC &&
		    checkpoints[i].pid == pid &&
		    checkpoints[i].timestamp_ns > newest_ts) {
			newest_ts = checkpoints[i].timestamp_ns;
			newest_idx = i;
		}
	}
	spin_unlock_irqrestore(&checkpoint_lock, flags);
	return newest_idx >= 0 ? &checkpoints[newest_idx] : NULL;
}
EXPORT_SYMBOL_GPL(eonix_checkpoint_get);

void eonix_checkpoint_clear(pid_t pid)
{
	int i;
	unsigned long flags;

	spin_lock_irqsave(&checkpoint_lock, flags);
	for (i = 0; i < MAX_CHECKPOINTS; i++) {
		if (checkpoints[i].pid == pid)
			checkpoints[i].valid = false;
	}
	spin_unlock_irqrestore(&checkpoint_lock, flags);
}
EXPORT_SYMBOL_GPL(eonix_checkpoint_clear);

/* ===== PART 3 — /proc/eonix/checkpoints ===== */

int eonix_checkpoints_show(struct seq_file *m, void *v)
{
	int i, j, count = 0;
	unsigned long flags;

	spin_lock_irqsave(&checkpoint_lock, flags);
	for (i = 0; i < MAX_CHECKPOINTS; i++) {
		if (!checkpoints[i].valid ||
		    checkpoints[i].magic != CHECKPOINT_MAGIC)
			continue;
		count++;
		seq_printf(m, "CKPT pid=%d name=%s exe=%s saved_at=%lluns resources=[",
			   checkpoints[i].pid,
			   checkpoints[i].comm,
			   checkpoints[i].exe_path[0] ?
				checkpoints[i].exe_path : "(unknown)",
			   checkpoints[i].timestamp_ns);
		for (j = 0; j < checkpoints[i].held_count; j++)
			seq_printf(m, "%s%d", j ? "," : "",
				   checkpoints[i].held_resources[j]);
		seq_puts(m, "]\n");
	}
	spin_unlock_irqrestore(&checkpoint_lock, flags);

	if (count == 0)
		seq_puts(m, "(no checkpoints)\n");
	return 0;
}
EXPORT_SYMBOL_GPL(eonix_checkpoints_show);

void eonix_checkpoint_init(void)
{
	memset(checkpoints, 0, sizeof(checkpoints));
	checkpoint_head = 0;
}
EXPORT_SYMBOL_GPL(eonix_checkpoint_init);
