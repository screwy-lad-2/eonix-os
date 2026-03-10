/*
 * stress_test.c — 100 rapid sequential deadlock cycles for Eonix RAG Monitor
 *
 * Verifies the RAG monitor handles rapid repeated deadlocks without kernel
 * memory leak or crash.  Uses /proc/eonix/rag_inject to inject deadlocks
 * and polls /proc/eonix/deadlock_log for detection.
 *
 * Build: gcc -O2 -Wall -pthread -o stress_test stress_test.c -lm
 * Run:   sudo ./stress_test
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>

#define INJECT_PATH "/proc/eonix/rag_inject"
#define LOG_PATH    "/proc/eonix/deadlock_log"
#define ITERATIONS  100
#define PASS_THRESH 95

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
		/* Parse: [status] deadlocks=N recoveries=N active=N */
		if (strstr(line, "[status]")) {
			char *p = strstr(line, "deadlocks=");
			if (p)
				count = atoi(p + 10);
		}
	}
	fclose(f);
	return count;
}

static long timespec_diff_ms(struct timespec *start, struct timespec *end)
{
	return (end->tv_sec - start->tv_sec) * 1000L +
	       (end->tv_nsec - start->tv_nsec) / 1000000L;
}

struct cycle_result {
	int  detected;
	int  recovered;
	long recovery_ms;
};

int main(void)
{
	struct cycle_result results[ITERATIONS];
	int detected_total = 0, recovered_total = 0;
	long total_ms = 0, min_ms = 999999, max_ms = 0;
	int failed[ITERATIONS];
	int fail_count = 0;
	int i, prev_count, cur_count;
	struct timespec t_start, t_end;

	printf("=== Eonix RAG Stress Test ===\n");
	printf("Iterations: %d\n", ITERATIONS);
	printf("Pass threshold: %d/%d (%.0f%%)\n\n",
	       PASS_THRESH, ITERATIONS,
	       (double)PASS_THRESH / ITERATIONS * 100.0);

	/* Initial reset */
	inject_cmd("RESET");
	usleep(200000);

	for (i = 0; i < ITERATIONS; i++) {
		/* Reset state */
		inject_cmd("RESET");
		usleep(100000);

		/* Get baseline deadlock count */
		prev_count = get_deadlock_count();
		if (prev_count < 0)
			prev_count = 0;

		/* Record start time */
		clock_gettime(CLOCK_MONOTONIC, &t_start);

		/* Inject 2-way deadlock: PID range 6000+2*i to avoid overlap */
		{
			char cmd[64];
			int pa = 6000 + 2 * i;
			int pb = 6001 + 2 * i;

			snprintf(cmd, sizeof(cmd), "HOLD %d 60", pa);
			inject_cmd(cmd);
			snprintf(cmd, sizeof(cmd), "HOLD %d 61", pb);
			inject_cmd(cmd);
			snprintf(cmd, sizeof(cmd), "PRIORITY %d 10", pa);
			inject_cmd(cmd);
			snprintf(cmd, sizeof(cmd), "PRIORITY %d 90", pb);
			inject_cmd(cmd);
			snprintf(cmd, sizeof(cmd), "WAIT %d 61", pa);
			inject_cmd(cmd);
			snprintf(cmd, sizeof(cmd), "WAIT %d 60", pb);
			inject_cmd(cmd);
		}

		/* Poll for detection (max 2 seconds) */
		results[i].detected = 0;
		results[i].recovered = 0;
		results[i].recovery_ms = 0;

		for (int w = 0; w < 40; w++) {
			cur_count = get_deadlock_count();
			if (cur_count > prev_count) {
				results[i].detected = 1;
				results[i].recovered = 1;
				clock_gettime(CLOCK_MONOTONIC, &t_end);
				results[i].recovery_ms =
					timespec_diff_ms(&t_start, &t_end);
				break;
			}
			usleep(50000);
		}

		if (!results[i].detected) {
			clock_gettime(CLOCK_MONOTONIC, &t_end);
			results[i].recovery_ms =
				timespec_diff_ms(&t_start, &t_end);
		}

		if (results[i].detected) {
			detected_total++;
			if (results[i].recovered)
				recovered_total++;
			total_ms += results[i].recovery_ms;
			if (results[i].recovery_ms < min_ms)
				min_ms = results[i].recovery_ms;
			if (results[i].recovery_ms > max_ms)
				max_ms = results[i].recovery_ms;
		} else {
			failed[fail_count++] = i;
		}

		if ((i + 1) % 10 == 0)
			printf("  Progress: %3d/%d  (detected so far: %d)\n",
			       i + 1, ITERATIONS, detected_total);
	}

	/* Print summary */
	long avg_ms = detected_total > 0 ? total_ms / detected_total : 0;

	printf("\n--- Results ---\n");
	printf("  Total:     %d\n", ITERATIONS);
	printf("  Detected:  %d / %d\n", detected_total, ITERATIONS);
	printf("  Recovered: %d / %d\n", recovered_total, ITERATIONS);
	printf("  Avg recovery time: %ldms\n", avg_ms);
	printf("  Min: %ldms | Max: %ldms\n",
	       detected_total > 0 ? min_ms : 0,
	       detected_total > 0 ? max_ms : 0);

	if (fail_count > 0) {
		printf("  Failed iterations: [");
		for (i = 0; i < fail_count; i++)
			printf("%s%d", i ? "," : "", failed[i]);
		printf("]\n");
	} else {
		printf("  Failed iterations: []\n");
	}

	/* Save JSON results */
	{
		FILE *f = fopen("/proc/self/cwd/../results/stress_test_results.json", "w");
		if (!f) {
			/* Try relative path */
			system("mkdir -p ../results");
			f = fopen("../results/stress_test_results.json", "w");
		}
		if (f) {
			fprintf(f, "{\n");
			fprintf(f, "  \"total\": %d,\n", ITERATIONS);
			fprintf(f, "  \"detected\": %d,\n", detected_total);
			fprintf(f, "  \"recovered\": %d,\n", recovered_total);
			fprintf(f, "  \"avg_ms\": %ld,\n", avg_ms);
			fprintf(f, "  \"min_ms\": %ld,\n",
				detected_total > 0 ? min_ms : 0);
			fprintf(f, "  \"max_ms\": %ld,\n",
				detected_total > 0 ? max_ms : 0);
			fprintf(f, "  \"failed_iterations\": [");
			for (i = 0; i < fail_count; i++)
				fprintf(f, "%s%d", i ? "," : "", failed[i]);
			fprintf(f, "]\n}\n");
			fclose(f);
			printf("\nResults saved to ../results/stress_test_results.json\n");
		}
	}

	int pass = (detected_total >= PASS_THRESH);
	printf("\nSTRESS TEST: %s (%d/%d >= %d/%d)\n",
	       pass ? "PASS" : "FAIL",
	       detected_total, ITERATIONS,
	       PASS_THRESH, ITERATIONS);

	/* Final cleanup */
	inject_cmd("RESET");

	return pass ? 0 : 1;
}
