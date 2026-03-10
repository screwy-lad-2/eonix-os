/* SPDX-License-Identifier: GPL-2.0 OR MIT */
/*
 * Eonix OS — eBPF Syscall Security Monitor
 * Shared header between BPF kernel program and userspace loader.
 */
#ifndef EONIX_SYSCALL_MONITOR_H
#define EONIX_SYSCALL_MONITOR_H

/* Portable type definitions for non-kernel builds (IntelliSense, userspace) */
#if !defined(__KERNEL__) && !defined(__BPF__) && !defined(_LINUX_TYPES_H)
#include <stdint.h>
typedef uint8_t  __u8;
typedef uint32_t __u32;
typedef uint64_t __u64;
#endif

#ifndef TASK_COMM_LEN
#define TASK_COMM_LEN 16
#endif
#define MAX_TRACKED_PIDS 4096
#define RING_BUF_SIZE (256 * 1024) /* 256 KB */

/* Syscall IDs we care about (x86-64 numbers) */
#define SYS_EXECVE   59
#define SYS_OPEN     2
#define SYS_OPENAT   257
#define SYS_CONNECT  42
#define SYS_ACCEPT   43
#define SYS_KILL     62
#define SYS_PTRACE   101

/* Event types */
enum event_type {
	EVENT_EXEC    = 0,
	EVENT_OPEN    = 1,
	EVENT_CONNECT = 2,
	EVENT_ACCEPT  = 3,
	EVENT_KILL    = 4,
	EVENT_PTRACE  = 5,
	EVENT_GENERIC = 6,
};

struct syscall_event {
	__u64 timestamp_ns;
	__u32 pid;
	__u32 tgid;
	__u32 uid;
	__u32 syscall_nr;
	__u8  event_type;
	__u8  pad[3];
	char  comm[TASK_COMM_LEN];
};

/* Per-PID statistics stored in hash map */
struct pid_stats {
	__u64 total_syscalls;
	__u64 exec_count;
	__u64 open_count;
	__u64 connect_count;
	__u64 accept_count;
	__u64 kill_count;
	__u64 ptrace_count;
	__u64 first_seen_ns;
	__u64 last_seen_ns;
};

#endif /* EONIX_SYSCALL_MONITOR_H */
