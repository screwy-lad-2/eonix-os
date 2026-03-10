// SPDX-License-Identifier: MIT
/*
 * Eonix OS — eBPF Syscall Security Monitor (userspace loader)
 *
 * Loads the compiled BPF object, attaches tracepoints, and polls
 * the ring buffer for syscall events.
 *
 * Build: gcc -O2 -Wall -o syscall_monitor syscall_monitor.c -lbpf -lelf -lz
 * Usage: sudo ./syscall_monitor
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>
#include "syscall_monitor.h"

static volatile sig_atomic_t running = 1;

static void sig_handler(int sig)
{
	(void)sig;
	running = 0;
}

static const char *event_type_str(int type)
{
	switch (type) {
	case EVENT_EXEC:    return "EXEC";
	case EVENT_OPEN:    return "OPEN";
	case EVENT_CONNECT: return "CONNECT";
	case EVENT_ACCEPT:  return "ACCEPT";
	case EVENT_KILL:    return "KILL";
	case EVENT_PTRACE:  return "PTRACE";
	case EVENT_GENERIC: return "GENERIC";
	default:            return "UNKNOWN";
	}
}

static int handle_event(void *ctx, void *data, size_t data_sz)
{
	(void)ctx;
	if (data_sz < sizeof(struct syscall_event))
		return 0;

	const struct syscall_event *e = data;
	struct timespec ts;
	clock_gettime(CLOCK_REALTIME, &ts);

	printf("[%ld.%06ld] pid=%-6u uid=%-5u %-8s syscall=%-3u %s\n",
		ts.tv_sec, ts.tv_nsec / 1000,
		e->pid, e->uid,
		event_type_str(e->event_type),
		e->syscall_nr, e->comm);
	return 0;
}

int main(int argc, char **argv)
{
	(void)argc;
	(void)argv;

	struct bpf_object *obj = NULL;
	struct ring_buffer *rb = NULL;
	int err;

	signal(SIGINT, sig_handler);
	signal(SIGTERM, sig_handler);

	/* Load BPF object */
	obj = bpf_object__open_file("syscall_monitor.bpf.o", NULL);
	if (libbpf_get_error(obj)) {
		fprintf(stderr, "ERROR: failed to open BPF object: %s\n",
			strerror(errno));
		return 1;
	}

	err = bpf_object__load(obj);
	if (err) {
		fprintf(stderr, "ERROR: failed to load BPF object: %s\n",
			strerror(-err));
		goto cleanup;
	}

	/* Attach all programs */
	struct bpf_program *prog;
	bpf_object__for_each_program(prog, obj) {
		struct bpf_link *link = bpf_program__attach(prog);
		if (libbpf_get_error(link)) {
			fprintf(stderr, "WARN: failed to attach %s: %s\n",
				bpf_program__name(prog), strerror(errno));
			/* Non-fatal: some tracepoints may not exist on all kernels */
		}
	}

	/* Set up ring buffer polling */
	int rb_fd = bpf_object__find_map_fd_by_name(obj, "events");
	if (rb_fd < 0) {
		fprintf(stderr, "ERROR: can't find 'events' ring buffer map\n");
		err = 1;
		goto cleanup;
	}

	rb = ring_buffer__new(rb_fd, handle_event, NULL, NULL);
	if (libbpf_get_error(rb)) {
		fprintf(stderr, "ERROR: failed to create ring buffer: %s\n",
			strerror(errno));
		err = 1;
		goto cleanup;
	}

	printf("Eonix eBPF Syscall Monitor running... (Ctrl+C to stop)\n");
	printf("%-20s %-8s %-7s %-10s %-7s %s\n",
		"TIMESTAMP", "PID", "UID", "TYPE", "NR", "COMM");

	/* Poll loop */
	while (running) {
		err = ring_buffer__poll(rb, 100 /* ms timeout */);
		if (err < 0 && err != -EINTR) {
			fprintf(stderr, "ERROR: ring buffer poll: %s\n",
				strerror(-err));
			break;
		}
	}

	printf("\nShutting down...\n");
	err = 0;

cleanup:
	ring_buffer__free(rb);
	bpf_object__close(obj);
	return err ? 1 : 0;
}
