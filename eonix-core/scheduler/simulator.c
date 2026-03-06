/*
 * Eonix OS — CPU Scheduler Simulator
 * ====================================
 * Implements FCFS, SJF, Round Robin, Priority, and a placeholder for
 * the ML-predictive scheduling mode. Used for benchmarking and
 * understanding scheduling algorithms before kernel integration.
 *
 * Build: gcc -O2 -o simulator simulator.c -lm
 * Run:   ./simulator
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>

#define MAX_PROCESSES 100

typedef struct {
    int pid;
    int arrival_time;
    int burst_time;
    int remaining_time;
    int priority;        /* Lower = higher priority */
    int start_time;
    int completion_time;
    int waiting_time;
    int turnaround_time;
    bool completed;
} Process;

/* ---- FCFS (First Come First Served) ---- */

void fcfs(Process procs[], int n)
{
    int current_time = 0;

    printf("\n=== FCFS Scheduling ===\n");

    for (int i = 0; i < n; i++) {
        if (current_time < procs[i].arrival_time)
            current_time = procs[i].arrival_time;

        procs[i].start_time = current_time;
        procs[i].completion_time = current_time + procs[i].burst_time;
        procs[i].turnaround_time =
            procs[i].completion_time - procs[i].arrival_time;
        procs[i].waiting_time =
            procs[i].turnaround_time - procs[i].burst_time;
        current_time = procs[i].completion_time;

        printf("  P%d: start=%d end=%d wait=%d turnaround=%d\n",
               procs[i].pid, procs[i].start_time,
               procs[i].completion_time, procs[i].waiting_time,
               procs[i].turnaround_time);
    }
}

/* ---- SJF (Shortest Job First, non-preemptive) ---- */

void sjf(Process procs[], int n)
{
    int current_time = 0;
    int completed = 0;

    printf("\n=== SJF Scheduling ===\n");

    for (int i = 0; i < n; i++)
        procs[i].completed = false;

    while (completed < n) {
        int shortest = -1;
        int min_burst = __INT_MAX__;

        for (int i = 0; i < n; i++) {
            if (!procs[i].completed &&
                procs[i].arrival_time <= current_time &&
                procs[i].burst_time < min_burst) {
                min_burst = procs[i].burst_time;
                shortest = i;
            }
        }

        if (shortest == -1) {
            current_time++;
            continue;
        }

        procs[shortest].start_time = current_time;
        procs[shortest].completion_time =
            current_time + procs[shortest].burst_time;
        procs[shortest].turnaround_time =
            procs[shortest].completion_time - procs[shortest].arrival_time;
        procs[shortest].waiting_time =
            procs[shortest].turnaround_time - procs[shortest].burst_time;
        procs[shortest].completed = true;
        current_time = procs[shortest].completion_time;
        completed++;

        printf("  P%d: start=%d end=%d wait=%d turnaround=%d\n",
               procs[shortest].pid, procs[shortest].start_time,
               procs[shortest].completion_time,
               procs[shortest].waiting_time,
               procs[shortest].turnaround_time);
    }
}

/* ---- Round Robin ---- */

void round_robin(Process procs[], int n, int quantum)
{
    int current_time = 0;
    int completed = 0;
    int queue[MAX_PROCESSES];
    int front = 0, rear = 0;

    printf("\n=== Round Robin (quantum=%d) ===\n", quantum);

    for (int i = 0; i < n; i++) {
        procs[i].remaining_time = procs[i].burst_time;
        procs[i].start_time = -1;
    }

    /* Enqueue first arriving process */
    queue[rear++] = 0;

    while (completed < n) {
        if (front == rear) {
            /* No process ready — advance time */
            current_time++;
            for (int i = 0; i < n; i++) {
                if (!procs[i].completed &&
                    procs[i].arrival_time <= current_time &&
                    procs[i].remaining_time > 0) {
                    queue[rear++] = i;
                    break;
                }
            }
            continue;
        }

        int idx = queue[front++];

        if (procs[idx].start_time == -1)
            procs[idx].start_time = current_time;

        int exec_time = (procs[idx].remaining_time < quantum)
                            ? procs[idx].remaining_time
                            : quantum;
        current_time += exec_time;
        procs[idx].remaining_time -= exec_time;

        /* Check for new arrivals during this quantum */
        for (int i = 0; i < n; i++) {
            if (i != idx && !procs[i].completed &&
                procs[i].arrival_time <= current_time &&
                procs[i].remaining_time == procs[i].burst_time) {
                queue[rear++] = i;
            }
        }

        if (procs[idx].remaining_time > 0) {
            queue[rear++] = idx; /* Re-enqueue */
        } else {
            procs[idx].completed = true;
            procs[idx].completion_time = current_time;
            procs[idx].turnaround_time =
                procs[idx].completion_time - procs[idx].arrival_time;
            procs[idx].waiting_time =
                procs[idx].turnaround_time - procs[idx].burst_time;
            completed++;

            printf("  P%d: end=%d wait=%d turnaround=%d\n",
                   procs[idx].pid, procs[idx].completion_time,
                   procs[idx].waiting_time, procs[idx].turnaround_time);
        }
    }
}

/* ---- Print summary ---- */

void print_summary(Process procs[], int n, const char *algo_name)
{
    double avg_wait = 0, avg_turnaround = 0;
    for (int i = 0; i < n; i++) {
        avg_wait += procs[i].waiting_time;
        avg_turnaround += procs[i].turnaround_time;
    }
    printf("[%s] Avg waiting=%.2f  Avg turnaround=%.2f\n\n",
           algo_name, avg_wait / n, avg_turnaround / n);
}

/* ---- Main ---- */

int main(void)
{
    /* Sample workload */
    Process procs[] = {
        {.pid = 1, .arrival_time = 0, .burst_time = 6, .priority = 2},
        {.pid = 2, .arrival_time = 1, .burst_time = 8, .priority = 1},
        {.pid = 3, .arrival_time = 2, .burst_time = 7, .priority = 4},
        {.pid = 4, .arrival_time = 3, .burst_time = 3, .priority = 3},
        {.pid = 5, .arrival_time = 4, .burst_time = 4, .priority = 5},
    };
    int n = sizeof(procs) / sizeof(procs[0]);

    printf("Eonix OS — Scheduler Simulator\n");
    printf("================================\n");
    printf("Processes: %d\n", n);

    /* Make copies for each algorithm */
    Process copy[MAX_PROCESSES];

    memcpy(copy, procs, sizeof(Process) * n);
    fcfs(copy, n);
    print_summary(copy, n, "FCFS");

    memcpy(copy, procs, sizeof(Process) * n);
    sjf(copy, n);
    print_summary(copy, n, "SJF");

    memcpy(copy, procs, sizeof(Process) * n);
    round_robin(copy, n, 3);
    print_summary(copy, n, "RR(3)");

    printf("TODO: ML-Predictive mode (integrate ONNX model after training)\n");

    return 0;
}
