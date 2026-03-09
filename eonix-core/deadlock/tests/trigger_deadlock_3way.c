/*
 * trigger_deadlock_3way.c — 3-way circular deadlock injection test
 *
 * Usage: sudo ./trigger_deadlock_3way
 *
 * Creates a 3-process cycle:
 *   P3001 holds R1, waits R2
 *   P3002 holds R2, waits R3
 *   P3003 holds R3, waits R1
 *
 * Build: gcc -O2 -Wall -pthread -o trigger_deadlock_3way trigger_deadlock_3way.c
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

	printf("=== Eonix 3-Way Deadlock Trigger Test ===\n\n");

	/* Reset */
	printf("[1] Resetting RAG state...\n");
	inject_cmd("RESET");

	/* Set up 3 processes with different priorities */
	printf("[2] Injecting 3 processes:\n");
	inject_cmd("HOLD 3001 30");  /* P3001 holds R30 */
	inject_cmd("HOLD 3002 31");  /* P3002 holds R31 */
	inject_cmd("HOLD 3003 32");  /* P3003 holds R32 */

	inject_cmd("PRIORITY 3001 20");  /* lowest = victim */
	inject_cmd("PRIORITY 3002 60");
	inject_cmd("PRIORITY 3003 90");  /* highest = survivor */

	/* Create 3-way circular wait */
	printf("[3] Creating 3-way cycle:\n");
	printf("    P3001(R30) → waits R31\n");
	printf("    P3002(R31) → waits R32\n");
	printf("    P3003(R32) → waits R30\n");

	inject_cmd("WAIT 3001 31");  /* P3001 waits for R31 (held by P3002) */
	inject_cmd("WAIT 3002 32");  /* P3002 waits for R32 (held by P3003) */
	inject_cmd("WAIT 3003 30");  /* P3003 waits for R30 (held by P3001) */

	/* Show RAG before detection */
	printf("\n[4] RAG state before detection:\n");
	if (read_proc(STATE_PATH, buf, sizeof(buf)) == 0)
		printf("%s\n", buf);

	/* Wait for detection */
	printf("[5] Waiting 2s for detection...\n");
	sleep(2);

	/* Check results */
	printf("[6] Checking deadlock_log:\n");
	if (read_proc(LOG_PATH, buf, sizeof(buf)) == 0) {
		printf("%s\n", buf);

		if (strstr(buf, "DEADLOCK_DETECTED")) {
			printf("  ✓ 3-way deadlock DETECTED\n");
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

		/* Victim should be P3001 (lowest priority=20) */
		if (strstr(buf, "victim=3001")) {
			printf("  ✓ Correct victim (PID 3001, lowest priority)\n");
		} else {
			printf("  ✗ Wrong victim selected!\n");
			pass = 0;
		}

		/* Verify all 3 PIDs appear in cycle */
		if (strstr(buf, "3001") && strstr(buf, "3002") && strstr(buf, "3003")) {
			printf("  ✓ All 3 PIDs in cycle detection\n");
		} else {
			printf("  ~ Not all PIDs listed in log (partial cycle match)\n");
		}
	} else {
		printf("  ✗ Could not read deadlock_log!\n");
		pass = 0;
	}

	/* Final state */
	printf("\n[7] RAG state after recovery:\n");
	if (read_proc(STATE_PATH, buf, sizeof(buf)) == 0)
		printf("%s\n", buf);

	/* Clean up */
	inject_cmd("RESET");

	printf("=== RESULT: %s ===\n", pass ? "ALL TESTS PASSED" : "SOME TESTS FAILED");
	return pass ? 0 : 1;
}
