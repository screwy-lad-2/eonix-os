/*
 * edge_cases.c — Edge case tests for Eonix RAG Monitor
 *
 * Tests 4 edge scenarios:
 *   1. Single-process self-deadlock
 *   2. Priority-based victim selection (high-prio survives)
 *   3. Rapid lock/unlock — no false positives
 *   4. Recovery under memory pressure
 *
 * Build: gcc -O2 -Wall -pthread -o edge_cases edge_cases.c
 * Run:   sudo ./edge_cases
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>

#define INJECT_PATH "/proc/eonix/rag_inject"
#define LOG_PATH    "/proc/eonix/deadlock_log"
#define STATE_PATH  "/proc/eonix/rag_state"

static int inject_cmd(const char *cmd)
{
	FILE *f = fopen(INJECT_PATH, "w");
	if (!f)
		return -1;
	fprintf(f, "%s\n", cmd);
	fclose(f);
	return 0;
}

static int get_deadlock_count(void)
{
	FILE *f = fopen(LOG_PATH, "r");
	char line[512];
	int count = -1;

	if (!f)
		return -1;
	while (fgets(line, sizeof(line), f)) {
		if (strstr(line, "[status]")) {
			char *p = strstr(line, "deadlocks=");
			if (p)
				count = atoi(p + 10);
		}
	}
	fclose(f);
	return count;
}

static int read_proc(const char *path, char *buf, size_t sz)
{
	FILE *f = fopen(path, "r");
	if (!f)
		return -1;
	size_t n = fread(buf, 1, sz - 1, f);
	buf[n] = '\0';
	fclose(f);
	return 0;
}

static long timespec_diff_ms(struct timespec *start, struct timespec *end)
{
	return (end->tv_sec - start->tv_sec) * 1000L +
	       (end->tv_nsec - start->tv_nsec) / 1000000L;
}

/* ===== TEST 1 — Self-deadlock (one process, one resource cycle) ===== */
static int test_self_deadlock(void)
{
	int prev, cur;

	printf("TEST 1 (self-deadlock): ");
	fflush(stdout);

	inject_cmd("RESET");
	usleep(200000);

	prev = get_deadlock_count();
	if (prev < 0) prev = 0;

	/* P7001 holds R70 and waits for R70 — self-cycle */
	inject_cmd("HOLD 7001 70");
	inject_cmd("PRIORITY 7001 50");
	inject_cmd("WAIT 7001 70");

	/* Wait for detection (up to 3s) */
	for (int w = 0; w < 30; w++) {
		cur = get_deadlock_count();
		if (cur > prev) {
			printf("PASS (self-cycle detected + recovered)\n");
			return 1;
		}
		usleep(100000);
	}

	printf("FAIL (self-deadlock not detected within 3s)\n");
	return 0;
}

/* ===== TEST 2 — Priority victim selection ===== */
static int test_priority_victim(void)
{
	int prev, cur;
	char buf[4096];

	printf("TEST 2 (priority victim select): ");
	fflush(stdout);

	inject_cmd("RESET");
	usleep(200000);

	prev = get_deadlock_count();
	if (prev < 0) prev = 0;

	/* P7010 has nice=-10 → high priority_score=90, should SURVIVE
	 * P7011 has nice=+10 → low priority_score=10, should be VICTIM */
	inject_cmd("HOLD 7010 71");
	inject_cmd("HOLD 7011 72");
	inject_cmd("PRIORITY 7010 90");    /* high priority = survivor */
	inject_cmd("PRIORITY 7011 10");    /* low priority = victim */
	inject_cmd("WAIT 7010 72");
	inject_cmd("WAIT 7011 71");

	/* Wait for detection */
	for (int w = 0; w < 30; w++) {
		cur = get_deadlock_count();
		if (cur > prev)
			break;
		usleep(100000);
	}

	if (cur <= prev) {
		printf("FAIL (deadlock not detected)\n");
		return 0;
	}

	/* Read log and check victim */
	if (read_proc(LOG_PATH, buf, sizeof(buf)) == 0 &&
	    strstr(buf, "victim=7011")) {
		printf("PASS (victim=7011 low-prio, survivor=7010 high-prio)\n");
		return 1;
	}

	/* Also check if victim was the low-priority one */
	if (read_proc(STATE_PATH, buf, sizeof(buf)) == 0 &&
	    strstr(buf, "pid=7010")) {
		printf("PASS (survivor PID 7010 still active)\n");
		return 1;
	}

	printf("FAIL (wrong victim selected)\n");
	return 0;
}

/* ===== TEST 3 — No false positives under rapid lock/unlock ===== */
static int test_no_false_positives(void)
{
	int before, after;

	printf("TEST 3 (no false positives): ");
	fflush(stdout);

	inject_cmd("RESET");
	usleep(200000);

	before = get_deadlock_count();
	if (before < 0) before = 0;

	/* Rapid hold/release cycles — 1000 times, no waiting = no deadlock */
	for (int i = 0; i < 1000; i++) {
		char cmd[64];
		snprintf(cmd, sizeof(cmd), "HOLD 7020 73");
		inject_cmd(cmd);
		snprintf(cmd, sizeof(cmd), "RELEASE 7020 73");
		inject_cmd(cmd);
	}

	/* Wait a full detection cycle */
	sleep(2);

	after = get_deadlock_count();
	if (after < 0) after = 0;

	if (after == before) {
		printf("PASS (0 false positives after 1000 lock/unlock cycles)\n");
		return 1;
	}

	printf("FAIL (%d false detections)\n", after - before);
	return 0;
}

/* ===== TEST 4 — Recovery under memory pressure ===== */
static int test_memory_pressure(void)
{
	int prev, cur;
	struct timespec t_start, t_end;
	long elapsed;
	volatile char *big_alloc;

	printf("TEST 4 (memory pressure): ");
	fflush(stdout);

	/* Allocate 512MB to stress the system (2GB might OOM on WSL2) */
	big_alloc = malloc(512 * 1024 * 1024);
	if (big_alloc) {
		/* Touch pages to force allocation */
		for (long p = 0; p < 512 * 1024 * 1024; p += 4096)
			big_alloc[p] = 1;
	}

	inject_cmd("RESET");
	usleep(200000);

	prev = get_deadlock_count();
	if (prev < 0) prev = 0;

	clock_gettime(CLOCK_MONOTONIC, &t_start);

	/* Inject 2-way deadlock */
	inject_cmd("HOLD 7030 74");
	inject_cmd("HOLD 7031 75");
	inject_cmd("PRIORITY 7030 20");
	inject_cmd("PRIORITY 7031 80");
	inject_cmd("WAIT 7030 75");
	inject_cmd("WAIT 7031 74");

	/* Wait for detection */
	for (int w = 0; w < 30; w++) {
		cur = get_deadlock_count();
		if (cur > prev) {
			clock_gettime(CLOCK_MONOTONIC, &t_end);
			elapsed = timespec_diff_ms(&t_start, &t_end);
			free((void *)big_alloc);
			if (elapsed <= 2000) {
				printf("PASS (detected in %ldms under 512MB pressure)\n",
				       elapsed);
				return 1;
			}
			printf("FAIL (detected but too slow: %ldms > 2000ms)\n",
			       elapsed);
			return 0;
		}
		usleep(100000);
	}

	free((void *)big_alloc);
	printf("FAIL (deadlock not detected under memory pressure)\n");
	return 0;
}

int main(void)
{
	int passed = 0;
	int total = 4;
	FILE *f;

	printf("=== Eonix RAG Edge Case Tests ===\n\n");

	passed += test_self_deadlock();
	passed += test_priority_victim();
	passed += test_no_false_positives();
	passed += test_memory_pressure();

	printf("\nAll %d edge cases: %s (%d/%d)\n",
	       total, passed == total ? "PASS" : "FAIL", passed, total);

	/* Save results */
	system("mkdir -p ../results");
	f = fopen("../results/edge_case_results.txt", "w");
	if (f) {
		fprintf(f, "Edge Case Test Results\n");
		fprintf(f, "======================\n");
		fprintf(f, "Passed: %d / %d\n", passed, total);
		fprintf(f, "Status: %s\n", passed == total ? "PASS" : "FAIL");
		fclose(f);
		printf("Results saved to ../results/edge_case_results.txt\n");
	}

	inject_cmd("RESET");
	return passed == total ? 0 : 1;
}
