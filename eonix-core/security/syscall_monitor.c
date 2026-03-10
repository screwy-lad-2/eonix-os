// SPDX-License-Identifier: MIT
/*
 * Eonix OS — eBPF Syscall Security Monitor Daemon (userspace)
 *
 * Modes:
 *   --monitor              Watch all syscall events in real time
 *   --block <pid> <level>  Add PID to blocked_pids (1=log,2=restrict,3=kill)
 *   --unblock <pid>        Remove PID from blocked_pids
 *   --status               Show all blocked PIDs + stats
 *   --top                  Show top 10 PIDs by syscall frequency
 *
 * Build: gcc -O2 -Wall -o syscall_monitor syscall_monitor.c -lbpf -lelf -lz
 * Usage: sudo ./syscall_monitor --monitor
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include <sys/stat.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>
#include "syscall_monitor.h"

/* ANSI color codes */
#define RED     "\033[1;31m"
#define YELLOW  "\033[1;33m"
#define GREEN   "\033[1;32m"
#define CYAN    "\033[1;36m"
#define RESET   "\033[0m"

static volatile sig_atomic_t running = 1;
static FILE *alert_log_fp;
static unsigned long stat_alerts;
static unsigned long stat_events;
static unsigned long stat_blocked;
static time_t last_stats_time;

/* ---- Signal handling ---- */

static void sig_handler(int sig)
{
	(void)sig;
	running = 0;
}

/* ---- Helpers ---- */

static const char *event_type_str(__u8 type)
{
	switch (type) {
	case EVENT_EXECVE:  return "EXECVE";
	case EVENT_OPENAT:  return "OPENAT";
	case EVENT_CONNECT: return "CONNECT";
	case EVENT_MMAP:    return "MMAP";
	case EVENT_FORK:    return "FORK";
	case EVENT_PTRACE:  return "PTRACE";
	case EVENT_SETUID:  return "SETUID";
	case EVENT_EXIT:    return "EXIT";
	default:            return "UNKNOWN";
	}
}

static const char *syscall_name(__u32 nr)
{
	switch (nr) {
	case SYS_EXECVE:  return "execve";
	case SYS_OPENAT:  return "openat";
	case SYS_CONNECT: return "connect";
	case SYS_MMAP:    return "mmap";
	case SYS_CLONE:   return "clone";
	case SYS_PTRACE:  return "ptrace";
	case SYS_SETUID:  return "setuid";
	default:          return "?";
	}
}

static void ensure_eonix_dir(void)
{
	const char *home = getenv("HOME");
	if (!home)
		home = "/tmp";
	char path[256];
	snprintf(path, sizeof(path), "%s/.eonix", home);
	mkdir(path, 0700);
}

static FILE *open_alert_log(void)
{
	const char *home = getenv("HOME");
	if (!home)
		home = "/tmp";
	char path[512];
	snprintf(path, sizeof(path), "%s/.eonix/security_alerts.log", home);
	return fopen(path, "a");
}

static void log_alert(const struct syscall_event *e, const char *action)
{
	if (!alert_log_fp)
		return;
	time_t now = time(NULL);
	struct tm *tm = gmtime(&now);
	char ts[64];
	strftime(ts, sizeof(ts), "%Y-%m-%dT%H:%M:%SZ", tm);
	fprintf(alert_log_fp, "%s | PID=%u | %s | %s | %s\n",
		ts, e->pid, e->comm, e->alert_type, action);
	fflush(alert_log_fp);
}

/* ---- Ring buffer event handler ---- */

static int handle_event(void *ctx, void *data, size_t data_sz)
{
	(void)ctx;
	if (data_sz < sizeof(struct syscall_event))
		return 0;

	const struct syscall_event *e = data;
	struct timespec ts;
	clock_gettime(CLOCK_REALTIME, &ts);

	stat_events++;

	int has_alert = (e->alert_type[0] != '\0');
	if (has_alert) {
		stat_alerts++;
		/* Red alert to terminal */
		fprintf(stdout,
			RED "[%ld.%03ld] ALERT: %-20s PID=%-6u UID=%-5u COMM=%-16s SYSCALL=%s"
			RESET "\n",
			(long)ts.tv_sec, ts.tv_nsec / 1000000,
			e->alert_type, e->pid, e->uid, e->comm,
			syscall_name(e->syscall_nr));
		const char *action = e->blocked ? "BLOCKED" : "LOG";
		log_alert(e, action);
	} else if (e->event_type == EVENT_EXIT) {
		/* Quiet for exits */
	} else {
		printf("[%ld.%03ld] PID=%-6u UID=%-5u %-8s SYSCALL=%-8s %s",
			(long)ts.tv_sec, ts.tv_nsec / 1000000,
			e->pid, e->uid,
			event_type_str(e->event_type),
			syscall_name(e->syscall_nr), e->comm);
		if (e->blocked) {
			stat_blocked++;
			printf("  " YELLOW "[BLOCKED]" RESET);
		}
		printf("\n");
	}
	return 0;
}

/* ---- Stats reporter (every 10 seconds) ---- */

static void maybe_print_stats(void)
{
	time_t now = time(NULL);
	if (now - last_stats_time < 10)
		return;
	last_stats_time = now;

	printf("\n" CYAN "=== Eonix Security Stats (last 10s) ===" RESET "\n");
	printf("Active events: %lu | Alerts: %lu | Blocked: %lu\n\n",
		stat_events, stat_alerts, stat_blocked);

	stat_events  = 0;
	stat_alerts  = 0;
	stat_blocked = 0;
}

/* ---- Mode: --monitor ---- */

static int do_monitor(void)
{
	struct bpf_object *obj = NULL;
	struct ring_buffer *rb = NULL;
	int err;

	ensure_eonix_dir();
	alert_log_fp = open_alert_log();
	if (!alert_log_fp)
		fprintf(stderr, "WARN: cannot open alert log\n");

	obj = bpf_object__open_file("syscall_monitor.bpf.o", NULL);
	if (libbpf_get_error(obj)) {
		fprintf(stderr, "ERROR: open BPF object: %s\n", strerror(errno));
		return 1;
	}

	err = bpf_object__load(obj);
	if (err) {
		fprintf(stderr, "ERROR: load BPF object: %s\n", strerror(-err));
		bpf_object__close(obj);
		return 1;
	}

	/* Pin maps so --block/--unblock/--status/--top can access them */
	struct bpf_map *m_blocked = bpf_object__find_map_by_name(obj, "blocked_pids");
	struct bpf_map *m_stats   = bpf_object__find_map_by_name(obj, "syscall_freq");
	if (m_blocked) {
		unlink(PIN_PATH_BLOCKED);
		bpf_map__pin(m_blocked, PIN_PATH_BLOCKED);
	}
	if (m_stats) {
		unlink(PIN_PATH_STATS);
		bpf_map__pin(m_stats, PIN_PATH_STATS);
	}

	/* Attach all programs */
	struct bpf_program *prog;
	bpf_object__for_each_program(prog, obj) {
		struct bpf_link *link = bpf_program__attach(prog);
		if (libbpf_get_error(link))
			fprintf(stderr, "WARN: attach %s: %s\n",
				bpf_program__name(prog), strerror(errno));
	}

	/* Ring buffer */
	int rb_fd = bpf_object__find_map_fd_by_name(obj, "events");
	if (rb_fd < 0) {
		fprintf(stderr, "ERROR: find events map\n");
		err = 1;
		goto cleanup;
	}

	rb = ring_buffer__new(rb_fd, handle_event, NULL, NULL);
	if (libbpf_get_error(rb)) {
		fprintf(stderr, "ERROR: create ring buffer: %s\n", strerror(errno));
		err = 1;
		goto cleanup;
	}

	printf(GREEN "Eonix eBPF Syscall Monitor running... (Ctrl+C to stop)" RESET "\n");
	printf("%-16s %-8s %-7s %-10s %-10s %s\n",
		"TIMESTAMP", "PID", "UID", "TYPE", "SYSCALL", "COMM");

	last_stats_time = time(NULL);

	while (running) {
		err = ring_buffer__poll(rb, 100);
		if (err < 0 && err != -EINTR)
			break;
		maybe_print_stats();
	}

	printf("\n" GREEN "Shutting down... Final stats: events=%lu alerts=%lu blocked=%lu"
		RESET "\n", stat_events, stat_alerts, stat_blocked);
	err = 0;

cleanup:
	ring_buffer__free(rb);
	unlink(PIN_PATH_BLOCKED);
	unlink(PIN_PATH_STATS);
	bpf_object__close(obj);
	if (alert_log_fp)
		fclose(alert_log_fp);
	return err ? 1 : 0;
}

/* ---- Mode: --block <pid> <level> ---- */

static int do_block(int pid, int level)
{
	if (level < 1 || level > 3) {
		fprintf(stderr, "ERROR: level must be 1 (log), 2 (restrict), or 3 (kill)\n");
		return 1;
	}

	int fd = bpf_obj_get(PIN_PATH_BLOCKED);
	if (fd < 0) {
		fprintf(stderr, "ERROR: open blocked_pids map (is --monitor running?): %s\n",
			strerror(errno));
		return 1;
	}

	__u32 key = (__u32)pid;
	__u8  val = (__u8)level;
	if (bpf_map_update_elem(fd, &key, &val, BPF_ANY)) {
		fprintf(stderr, "ERROR: update map: %s\n", strerror(errno));
		close(fd);
		return 1;
	}

	const char *labels[] = {"", "LOG", "RESTRICT", "KILL"};
	printf("PID %d blocked at level %d (%s)\n", pid, level, labels[level]);
	close(fd);
	return 0;
}

/* ---- Mode: --unblock <pid> ---- */

static int do_unblock(int pid)
{
	int fd = bpf_obj_get(PIN_PATH_BLOCKED);
	if (fd < 0) {
		fprintf(stderr, "ERROR: open blocked_pids map (is --monitor running?): %s\n",
			strerror(errno));
		return 1;
	}

	__u32 key = (__u32)pid;
	if (bpf_map_delete_elem(fd, &key))
		fprintf(stderr, "WARN: PID %d was not in blocked list\n", pid);
	else
		printf("PID %d unblocked\n", pid);

	close(fd);
	return 0;
}

/* ---- Mode: --status ---- */

static int do_status(void)
{
	int fd_b = bpf_obj_get(PIN_PATH_BLOCKED);
	int fd_s = bpf_obj_get(PIN_PATH_STATS);
	if (fd_b < 0 || fd_s < 0) {
		fprintf(stderr, "ERROR: open pinned maps (is --monitor running?)\n");
		if (fd_b >= 0) close(fd_b);
		if (fd_s >= 0) close(fd_s);
		return 1;
	}

	printf(CYAN "=== Blocked PIDs ===" RESET "\n");
	printf("%-8s %-8s %-16s\n", "PID", "LEVEL", "COMM");

	__u32 key = 0, next_key;
	__u8  level;
	int   count = 0;
	while (bpf_map_get_next_key(fd_b, &key, &next_key) == 0) {
		if (bpf_map_lookup_elem(fd_b, &next_key, &level) == 0) {
			struct pid_stats s = {};
			bpf_map_lookup_elem(fd_s, &next_key, &s);
			printf("%-8u %-8u %-16s\n", next_key, level, s.comm);
			count++;
		}
		key = next_key;
	}
	printf("Total: %d blocked\n", count);

	close(fd_b);
	close(fd_s);
	return 0;
}

/* ---- Mode: --top ---- */

struct top_entry {
	__u32 pid;
	__u64 total;
	char  comm[TASK_COMM_LEN];
};

static int do_top(void)
{
	int fd = bpf_obj_get(PIN_PATH_STATS);
	if (fd < 0) {
		fprintf(stderr, "ERROR: open syscall_freq map (is --monitor running?)\n");
		return 1;
	}

	struct top_entry top[10];
	memset(top, 0, sizeof(top));
	int top_count = 0;

	__u32 key = 0, next_key;
	struct pid_stats s;
	while (bpf_map_get_next_key(fd, &key, &next_key) == 0) {
		if (bpf_map_lookup_elem(fd, &next_key, &s) == 0) {
			__u64 total = s.execve_count + s.openat_count +
				      s.connect_count + s.mmap_count +
				      s.fork_count + s.ptrace_count +
				      s.setuid_count;
			/* Simple insertion into sorted top-10 */
			int pos = top_count < 10 ? top_count : -1;
			for (int i = 0; i < top_count && i < 10; i++) {
				if (total > top[i].total) {
					pos = i;
					break;
				}
			}
			if (pos >= 0 && pos < 10) {
				for (int i = 9; i > pos; i--)
					top[i] = top[i - 1];
				top[pos].pid   = next_key;
				top[pos].total = total;
				memcpy(top[pos].comm, s.comm, TASK_COMM_LEN);
				if (top_count < 10)
					top_count++;
			}
		}
		key = next_key;
	}

	printf(CYAN "=== Top %d Processes by Syscall Frequency ===" RESET "\n",
		top_count);
	printf("%-4s %-8s %-16s %-8s %-8s %-8s %-8s %-10s\n",
		"#", "PID", "COMM", "EXECVE", "OPENAT", "CONNECT", "FORK", "TOTAL");

	for (int i = 0; i < top_count; i++) {
		struct pid_stats st;
		memset(&st, 0, sizeof(st));
		bpf_map_lookup_elem(fd, &top[i].pid, &st);
		printf("%-4d %-8u %-16s %-8llu %-8llu %-8llu %-8llu %-10llu\n",
			i + 1, top[i].pid, top[i].comm,
			(unsigned long long)st.execve_count,
			(unsigned long long)st.openat_count,
			(unsigned long long)st.connect_count,
			(unsigned long long)st.fork_count,
			(unsigned long long)top[i].total);
	}

	close(fd);
	return 0;
}

/* ---- Usage ---- */

static void usage(const char *prog)
{
	fprintf(stderr,
		"Eonix eBPF Syscall Security Monitor\n\n"
		"Usage:\n"
		"  %s --monitor              Watch all syscall events\n"
		"  %s --block <pid> <level>  Block PID (1=log 2=restrict 3=kill)\n"
		"  %s --unblock <pid>        Unblock PID\n"
		"  %s --status               Show blocked PIDs\n"
		"  %s --top                  Show top 10 PIDs by frequency\n",
		prog, prog, prog, prog, prog);
}

/* ---- Main ---- */

int main(int argc, char **argv)
{
	signal(SIGINT,  sig_handler);
	signal(SIGTERM, sig_handler);

	if (argc < 2) {
		usage(argv[0]);
		return 1;
	}

	if (strcmp(argv[1], "--monitor") == 0)
		return do_monitor();
	else if (strcmp(argv[1], "--block") == 0 && argc >= 4)
		return do_block(atoi(argv[2]), atoi(argv[3]));
	else if (strcmp(argv[1], "--unblock") == 0 && argc >= 3)
		return do_unblock(atoi(argv[2]));
	else if (strcmp(argv[1], "--status") == 0)
		return do_status();
	else if (strcmp(argv[1], "--top") == 0)
		return do_top();
	else {
		usage(argv[0]);
		return 1;
	}
}
