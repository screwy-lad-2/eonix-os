// SPDX-License-Identifier: GPL-2.0
/*
 * Eonix OS — eBPF Syscall Security Monitor (BPF kernel program)
 *
 * Attaches to raw_syscalls tracepoints and dispatches events for
 * security-sensitive syscalls through a ring buffer.  Per-PID
 * statistics are accumulated in a BPF hash map.
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

/* ---------- maps ---------- */

struct {
	__uint(type, BPF_MAP_TYPE_RINGBUF);
	__uint(max_entries, RING_BUF_SIZE);
} events SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, MAX_TRACKED_PIDS);
	__type(key, __u32);
	__type(value, struct pid_stats);
} pid_stats_map SEC(".maps");

/* ---------- helpers ---------- */

static __always_inline void
emit_event(__u32 syscall_nr, __u8 event_type)
{
	struct syscall_event *e;
	__u64 pid_tgid = bpf_get_current_pid_tgid();
	__u32 pid  = (__u32)(pid_tgid >> 32);
	__u32 tgid = (__u32)pid_tgid;
	__u64 now  = bpf_ktime_get_ns();

	e = bpf_ringbuf_reserve(&events, sizeof(*e), 0);
	if (!e)
		return;

	e->timestamp_ns = now;
	e->pid          = pid;
	e->tgid         = tgid;
	e->uid          = (__u32)bpf_get_current_uid_gid();
	e->syscall_nr   = syscall_nr;
	e->event_type   = event_type;
	bpf_get_current_comm(e->comm, sizeof(e->comm));

	bpf_ringbuf_submit(e, 0);

	/* Update per-PID stats */
	struct pid_stats *s = bpf_map_lookup_elem(&pid_stats_map, &pid);
	if (s) {
		s->total_syscalls++;
		s->last_seen_ns = now;
		switch (event_type) {
		case EVENT_EXEC:    s->exec_count++;    break;
		case EVENT_OPEN:    s->open_count++;    break;
		case EVENT_CONNECT: s->connect_count++; break;
		case EVENT_ACCEPT:  s->accept_count++;  break;
		case EVENT_KILL:    s->kill_count++;     break;
		case EVENT_PTRACE:  s->ptrace_count++;  break;
		default: break;
		}
	} else {
		struct pid_stats new_stats = {
			.total_syscalls = 1,
			.first_seen_ns  = now,
			.last_seen_ns   = now,
		};
		switch (event_type) {
		case EVENT_EXEC:    new_stats.exec_count    = 1; break;
		case EVENT_OPEN:    new_stats.open_count    = 1; break;
		case EVENT_CONNECT: new_stats.connect_count = 1; break;
		case EVENT_ACCEPT:  new_stats.accept_count  = 1; break;
		case EVENT_KILL:    new_stats.kill_count    = 1; break;
		case EVENT_PTRACE:  new_stats.ptrace_count  = 1; break;
		default: break;
		}
		bpf_map_update_elem(&pid_stats_map, &pid, &new_stats, BPF_ANY);
	}
}

/* ---------- tracepoint handlers ---------- */

/*
 * 1. execve — process execution: potential code injection vector
 */
SEC("tracepoint/syscalls/sys_enter_execve")
int tp_execve(struct trace_event_raw_sys_enter *ctx)
{
	emit_event(SYS_EXECVE, EVENT_EXEC);
	return 0;
}

/*
 * 2. open — file access: sensitive file reads, data exfiltration
 */
SEC("tracepoint/syscalls/sys_enter_open")
int tp_open(struct trace_event_raw_sys_enter *ctx)
{
	emit_event(SYS_OPEN, EVENT_OPEN);
	return 0;
}

/*
 * 3. openat — modern variant of open (used by glibc wrappers)
 */
SEC("tracepoint/syscalls/sys_enter_openat")
int tp_openat(struct trace_event_raw_sys_enter *ctx)
{
	emit_event(SYS_OPENAT, EVENT_OPEN);
	return 0;
}

/*
 * 4. connect — outbound network connections
 */
SEC("tracepoint/syscalls/sys_enter_connect")
int tp_connect(struct trace_event_raw_sys_enter *ctx)
{
	emit_event(SYS_CONNECT, EVENT_CONNECT);
	return 0;
}

/*
 * 5. accept — inbound network connections (reverse shell, bind shell)
 */
SEC("tracepoint/syscalls/sys_enter_accept")
int tp_accept(struct trace_event_raw_sys_enter *ctx)
{
	emit_event(SYS_ACCEPT, EVENT_ACCEPT);
	return 0;
}

/*
 * 6. kill — signal delivery: process manipulation
 */
SEC("tracepoint/syscalls/sys_enter_kill")
int tp_kill(struct trace_event_raw_sys_enter *ctx)
{
	emit_event(SYS_KILL, EVENT_KILL);
	return 0;
}

/*
 * 7. ptrace — debugger attach / process injection
 */
SEC("tracepoint/syscalls/sys_enter_ptrace")
int tp_ptrace(struct trace_event_raw_sys_enter *ctx)
{
	emit_event(SYS_PTRACE, EVENT_PTRACE);
	return 0;
}
