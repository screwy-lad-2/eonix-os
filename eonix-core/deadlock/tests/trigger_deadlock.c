/*
 * trigger_deadlock.c — 2-way deadlock injection test for Eonix RAG Monitor
 *
 * Usage: sudo ./trigger_deadlock
 *
 * This program injects a 2-process circular wait into the kernel module's
 * RAG via /proc/eonix/rag_inject, waits for the detection timer to fire,
 * then reads /proc/eonix/deadlock_log to verify detection & recovery.
 *
 * Build: gcc -O2 -Wall -pthread -o trigger_deadlock trigger_deadlock.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define INJECT_PATH "/proc/eonix/rag_inject"
#define LOG_PATH    "/proc/eonix/deadlock_log"
#define STATE_PATH  "/proc/eonix/rag_state"

static int inject_cmd(const char *cmd)
{
	FILE *f = fopen(INJECT_PATH, "w");
	if (!f) {
		perror("fopen rag_inject");
		return -1;
	}
	fprintf(f, "%s\n", cmd);
	fclose(f);
	return 0;
}

static int read_proc(const char *path, char *buf, size_t sz)
{
	FILE *f = fopen(path, "r");
	if (!f) {
		perror(path);
		return -1;
	}
	size_t n = fread(buf, 1, sz - 1, f);
	buf[n] = '\0';
	fclose(f);
	return 0;
}

int main(void)
{
	char buf[4096];
	int pass = 1;

	printf("=== Eonix 2-Way Deadlock Trigger Test ===\n\n");

	/* Reset state */
	printf("[1] Resetting RAG state...\n");
	inject_cmd("RESET");

	/* Set up 2 processes with different priorities */
	printf("[2] Injecting processes with priorities...\n");
	inject_cmd("HOLD 2001 1");  /* P2001 holds R1 */
	inject_cmd("HOLD 2002 2");  /* P2002 holds R2 */
	inject_cmd("PRIORITY 2001 30");  /* lower prio = victim */
	inject_cmd("PRIORITY 2002 80");  /* higher prio = survivor */

	/* Create circular wait */
	printf("[3] Creating circular wait: P2001→R2, P2002→R1\n");
	inject_cmd("WAIT 2001 2");  /* P2001 waits for R2 (held by P2002) */
	inject_cmd("WAIT 2002 1");  /* P2002 waits for R1 (held by P2001) */

	/* Show RAG state before detection */
	printf("[4] RAG state before detection:\n");
	if (read_proc(STATE_PATH, buf, sizeof(buf)) == 0)
		printf("%s\n", buf);

	/* Wait for detection timer (500ms interval + margin) */
	printf("[5] Waiting 2s for detection timer...\n");
	sleep(2);

	/* Check results */
	printf("[6] Checking deadlock_log:\n");
	if (read_proc(LOG_PATH, buf, sizeof(buf)) == 0) {
		printf("%s\n", buf);

		/* Validate detection */
		if (strstr(buf, "DEADLOCK_DETECTED")) {
			printf("  ✓ Deadlock DETECTED\n");
		} else {
			printf("  ✗ Deadlock NOT detected!\n");
			pass = 0;
		}

		if (strstr(buf, "RECOVERY_COMPLETE")) {
			printf("  ✓ Recovery COMPLETED\n");
		} else {
			printf("  ✗ Recovery NOT completed!\n");
			pass = 0;
		}

		/* Verify victim selection (P2001 has lower priority) */
		if (strstr(buf, "victim=2001")) {
			printf("  ✓ Correct victim (PID 2001, lower priority)\n");
		} else {
			printf("  ✗ Wrong victim selected!\n");
			pass = 0;
		}
	} else {
		printf("  ✗ Could not read deadlock_log!\n");
		pass = 0;
	}

	/* Show final RAG state */
	printf("[7] RAG state after recovery:\n");
	if (read_proc(STATE_PATH, buf, sizeof(buf)) == 0) {
		printf("%s\n", buf);

		/* P2002 should still be active, P2001 should be gone */
		if (strstr(buf, "pid=2002")) {
			printf("  ✓ Survivor PID 2002 still active\n");
		} else {
			printf("  (PID 2002 state may have been cleaned)\n");
		}
	}

	/* Clean up */
	inject_cmd("RESET");

	printf("\n=== RESULT: %s ===\n", pass ? "ALL TESTS PASSED" : "SOME TESTS FAILED");
	return pass ? 0 : 1;
}
