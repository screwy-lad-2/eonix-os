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
typedef uint16_t __u16;
typedef uint32_t __u32;
typedef uint64_t __u64;
typedef int32_t  __s32;
#endif

#ifndef TASK_COMM_LEN
#define TASK_COMM_LEN 16
#endif

#define ALERT_LEN          24
#define MAX_TRACKED_PIDS   1024
#define RING_BUF_SIZE      (256 * 1024)  /* 256 KB */

/* Threshold constants */
#define EXEC_STORM_THRESHOLD   10
#define FORK_BOMB_THRESHOLD    20
#define PORT_SCAN_THRESHOLD    50
#define WINDOW_NS              1000000000ULL  /* 1 second */

/* Syscall IDs (x86-64) */
#define SYS_EXECVE   59
#define SYS_OPENAT   257
#define SYS_CONNECT  42
#define SYS_MMAP     9
#define SYS_CLONE    56
#define SYS_PTRACE   101
#define SYS_SETUID   105

/* BPF map pin paths */
#define PIN_PATH_BLOCKED "/sys/fs/bpf/eonix_blocked_pids"
#define PIN_PATH_STATS   "/sys/fs/bpf/eonix_syscall_freq"

/* Event types */
enum event_type {
	EVENT_EXECVE   = 0,
	EVENT_OPENAT   = 1,
	EVENT_CONNECT  = 2,
	EVENT_MMAP     = 3,
	EVENT_FORK     = 4,
	EVENT_PTRACE   = 5,
	EVENT_SETUID   = 6,
	EVENT_EXIT     = 7,
	EVENT_ALERT    = 8,
};

/* Ring buffer event structure */
struct syscall_event {
	__u64 timestamp_ns;
	__u32 pid;
	__u32 tgid;
	__u32 uid;
	__u32 syscall_nr;
	__u8  event_type;
	__u8  blocked;
	__u8  pad[2];
	char  comm[TASK_COMM_LEN];
	char  alert_type[ALERT_LEN];
};

/* Per-PID statistics stored in syscall_freq hash map */
struct pid_stats {
	__u64 execve_count;
	__u64 openat_count;
	__u64 connect_count;
	__u64 mmap_count;
	__u64 fork_count;
	__u64 ptrace_count;
	__u64 setuid_count;
	__u64 first_seen_ns;
	__u64 last_seen_ns;
	__u64 window_start_ns;
	char  comm[TASK_COMM_LEN];
};

#endif /* EONIX_SYSCALL_MONITOR_H */
