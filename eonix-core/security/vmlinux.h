/* SPDX-License-Identifier: (LGPL-2.1 OR BSD-2-Clause) */
/*
 * Minimal vmlinux.h for Eonix eBPF programs.
 *
 * This file provides the subset of kernel type definitions needed by
 * syscall_monitor.bpf.c.  On a live system with BTF enabled, a full
 * vmlinux.h can be generated via:
 *   bpftool btf dump file /sys/kernel/btf/vmlinux format c > vmlinux.h
 *
 * This stub exists so the BPF object can compile on CI runners that
 * lack /sys/kernel/btf/vmlinux.
 */
#ifndef __VMLINUX_H__
#define __VMLINUX_H__

typedef unsigned char  __u8;
typedef unsigned short __u16;
typedef unsigned int   __u32;
typedef unsigned long long __u64;
typedef signed char    __s8;
typedef signed short   __s16;
typedef signed int     __s32;
typedef signed long long __s64;

typedef __u8  u8;
typedef __u16 u16;
typedef __u32 u32;
typedef __u64 u64;
typedef __s8  s8;
typedef __s16 s16;
typedef __s32 s32;
typedef __s64 s64;

typedef _Bool bool;

enum {
	false = 0,
	true  = 1,
};

/* BPF map types used by our programs */
enum bpf_map_type {
	BPF_MAP_TYPE_HASH        = 1,
	BPF_MAP_TYPE_RINGBUF     = 27,
};

/* Tracepoint context — used by SEC("tracepoint/...") programs */
struct trace_event_raw_sys_enter {
	__u64  unused;
	long   id;
	unsigned long args[6];
};

struct trace_event_raw_sys_exit {
	__u64  unused;
	long   id;
	long   ret;
};

#define TASK_COMM_LEN 16

#endif /* __VMLINUX_H__ */
