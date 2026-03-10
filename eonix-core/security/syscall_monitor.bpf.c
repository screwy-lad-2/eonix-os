// SPDX-License-Identifier: GPL-2.0
/*
 * Eonix OS — eBPF Syscall Security Monitor (BPF kernel program)
 *
 * Hooks 7 security-sensitive syscall tracepoints plus sched_process_exit.
 * Per-PID enforcement via blocked_pids map (1=log, 2=restrict, 3=kill).
 * Windowed rate checking with alert emission through ring buffer.
 *
 * Maps:
 *   events       — RINGBUF   (stream syscall_event to userspace)
 *   blocked_pids — HASH      (u32 pid → u8 block_level)
 *   syscall_freq — HASH      (u32 pid → struct pid_stats)
 *
 * Build: clang -O2 -g -target bpf -c syscall_monitor.bpf.c -o syscall_monitor.bpf.o
 */

#define __BPF__ 1
#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>
#include "syscall_monitor.h"

char LICENSE[] SEC("license") = "GPL";

/* ========== BPF Maps ========== */

struct {
	__uint(type, BPF_MAP_TYPE_RINGBUF);
	__uint(max_entries, RING_BUF_SIZE);
} events SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, MAX_TRACKED_PIDS);
	__type(key, __u32);
	__type(value, __u8);
} blocked_pids SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, MAX_TRACKED_PIDS);
	__type(key, __u32);
	__type(value, struct pid_stats);
} syscall_freq SEC(".maps");

/* ========== Core Handler ========== */

static __always_inline int
handle_syscall(__u8 event_type, __u32 syscall_nr)
{
	__u64 pid_tgid = bpf_get_current_pid_tgid();
	__u32 pid  = (__u32)(pid_tgid >> 32);
	__u64 now  = bpf_ktime_get_ns();
	__u8  blocked = 0;
	char  alert[ALERT_LEN];

	__builtin_memset(alert, 0, sizeof(alert));

	/* --- Step 1: Check blocked_pids map --- */
	__u8 *level = bpf_map_lookup_elem(&blocked_pids, &pid);
	if (level) {
		if (*level == 1) {
			/* Log only — continue */
		} else if (*level == 2) {
			blocked = 1;
			bpf_send_signal(19); /* SIGSTOP */
		} else if (*level >= 3) {
			blocked = 1;
			bpf_send_signal(9);  /* SIGKILL */
		}
	}

	/* --- Step 2: Update syscall_freq map --- */
	struct pid_stats *s = bpf_map_lookup_elem(&syscall_freq, &pid);
	if (!s) {
		/* First syscall from this PID — create entry */
		struct pid_stats ns = {};
		ns.first_seen_ns   = now;
		ns.last_seen_ns    = now;
		ns.window_start_ns = now;
		bpf_get_current_comm(ns.comm, sizeof(ns.comm));

		switch (event_type) {
		case EVENT_EXECVE:  ns.execve_count  = 1; break;
		case EVENT_OPENAT:  ns.openat_count  = 1; break;
		case EVENT_CONNECT: ns.connect_count = 1; break;
		case EVENT_MMAP:    ns.mmap_count    = 1; break;
		case EVENT_FORK:    ns.fork_count    = 1; break;
		case EVENT_PTRACE:  ns.ptrace_count  = 1; break;
		case EVENT_SETUID:  ns.setuid_count  = 1; break;
		default: break;
		}

		bpf_map_update_elem(&syscall_freq, &pid, &ns, BPF_ANY);

		/* First-occurrence alerts */
		if (event_type == EVENT_PTRACE)
			__builtin_memcpy(alert, "ptrace_detected", 16);
		else if (event_type == EVENT_SETUID)
			__builtin_memcpy(alert, "privilege_escalation", 21);
	} else {
		/* Window expiry: reset rate counters every WINDOW_NS */
		__u64 elapsed = now - s->window_start_ns;
		if (elapsed >= WINDOW_NS) {
			s->execve_count    = 0;
			s->openat_count    = 0;
			s->connect_count   = 0;
			s->mmap_count      = 0;
			s->fork_count      = 0;
			s->window_start_ns = now;
		}

		/* Increment counter and check threshold */
		switch (event_type) {
		case EVENT_EXECVE:
			s->execve_count++;
			if (s->execve_count > EXEC_STORM_THRESHOLD)
				__builtin_memcpy(alert, "exec_storm", 11);
			break;
		case EVENT_OPENAT:
			s->openat_count++;
			break;
		case EVENT_CONNECT:
			s->connect_count++;
			if (s->connect_count > PORT_SCAN_THRESHOLD)
				__builtin_memcpy(alert, "port_scan", 10);
			break;
		case EVENT_MMAP:
			s->mmap_count++;
			break;
		case EVENT_FORK:
			s->fork_count++;
			if (s->fork_count > FORK_BOMB_THRESHOLD)
				__builtin_memcpy(alert, "fork_bomb", 10);
			break;
		case EVENT_PTRACE:
			s->ptrace_count++;
			__builtin_memcpy(alert, "ptrace_detected", 16);
			break;
		case EVENT_SETUID:
			s->setuid_count++;
			__builtin_memcpy(alert, "privilege_escalation", 21);
			break;
		default:
			break;
		}
		s->last_seen_ns = now;
	}

	/* --- Step 3: Emit ring buffer event --- */
	struct syscall_event *e;
	e = bpf_ringbuf_reserve(&events, sizeof(*e), 0);
	if (!e)
		return 0;

	e->timestamp_ns = now;
	e->pid          = pid;
	e->tgid         = (__u32)pid_tgid;
	e->uid          = (__u32)bpf_get_current_uid_gid();
	e->syscall_nr   = syscall_nr;
	e->event_type   = event_type;
	e->blocked      = blocked;
	e->pad[0]       = 0;
	e->pad[1]       = 0;
	bpf_get_current_comm(e->comm, sizeof(e->comm));
	__builtin_memcpy(e->alert_type, alert, ALERT_LEN);

	bpf_ringbuf_submit(e, 0);
	return 0;
}

/* ========== 7 Syscall Tracepoint Programs ========== */

SEC("tracepoint/syscalls/sys_enter_execve")
int tp_execve(struct trace_event_raw_sys_enter *ctx)
{
	return handle_syscall(EVENT_EXECVE, SYS_EXECVE);
}

SEC("tracepoint/syscalls/sys_enter_openat")
int tp_openat(struct trace_event_raw_sys_enter *ctx)
{
	return handle_syscall(EVENT_OPENAT, SYS_OPENAT);
}

SEC("tracepoint/syscalls/sys_enter_connect")
int tp_connect(struct trace_event_raw_sys_enter *ctx)
{
	return handle_syscall(EVENT_CONNECT, SYS_CONNECT);
}

SEC("tracepoint/syscalls/sys_enter_mmap")
int tp_mmap(struct trace_event_raw_sys_enter *ctx)
{
	return handle_syscall(EVENT_MMAP, SYS_MMAP);
}

SEC("tracepoint/syscalls/sys_enter_clone")
int tp_clone(struct trace_event_raw_sys_enter *ctx)
{
	return handle_syscall(EVENT_FORK, SYS_CLONE);
}

SEC("tracepoint/syscalls/sys_enter_ptrace")
int tp_ptrace(struct trace_event_raw_sys_enter *ctx)
{
	return handle_syscall(EVENT_PTRACE, SYS_PTRACE);
}

SEC("tracepoint/syscalls/sys_enter_setuid")
int tp_setuid(struct trace_event_raw_sys_enter *ctx)
{
	return handle_syscall(EVENT_SETUID, SYS_SETUID);
}

/* ========== Process Exit Cleanup ========== */

SEC("tracepoint/sched/sched_process_exit")
int tp_sched_exit(struct trace_event_raw_sched_process_exit *ctx)
{
	__u64 pid_tgid = bpf_get_current_pid_tgid();
	__u32 pid = (__u32)(pid_tgid >> 32);
	__u64 now = bpf_ktime_get_ns();

	/* Remove PID from tracking maps */
	bpf_map_delete_elem(&syscall_freq, &pid);
	bpf_map_delete_elem(&blocked_pids, &pid);

	/* Emit EXIT event */
	struct syscall_event *e;
	e = bpf_ringbuf_reserve(&events, sizeof(*e), 0);
	if (!e)
		return 0;

	__builtin_memset(e, 0, sizeof(*e));
	e->timestamp_ns = now;
	e->pid          = pid;
	e->tgid         = (__u32)pid_tgid;
	e->uid          = (__u32)bpf_get_current_uid_gid();
	e->event_type   = EVENT_EXIT;
	bpf_get_current_comm(e->comm, sizeof(e->comm));

	bpf_ringbuf_submit(e, 0);
	return 0;
}
