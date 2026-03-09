/*
 * Eonix OS — CPU Scheduler Simulator
 * ====================================
 * Implements FCFS, SJF, Round Robin, and Priority (preemptive).
 *
 * Features:
 *   - Read input from CSV file (pid,arrival_time,burst_time,priority)
 *   - ASCII Gantt chart output
 *   - Comparison table with Avg Wait, Avg TAT, CPU%, Throughput
 *   - JSON export to results/scheduler_results.json
 *   - CLI: --algo fcfs|sjf|rr|priority|all  --input <file>
 *
 * Build: gcc -O2 -o simulator simulator.c -lm
 * Run:   ./simulator --algo all --input processes.csv
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <math.h>

#define MAX_PROCESSES 100
#define MAX_GANTT     2048
#define RR_QUANTUM    4

typedef struct {
    int pid;
    int arrival_time;
    int burst_time;
    int remaining_time;
    int priority;        /* Lower number = higher priority */
    int start_time;
    int completion_time;
    int waiting_time;
    int turnaround_time;
    bool completed;
} Process;

/* Gantt chart entry */
typedef struct {
    int pid;
    int start;
    int end;
} GanttEntry;

/* Algorithm metrics */
typedef struct {
    char name[16];
    double avg_wait;
    double avg_tat;
    double cpu_util;
    double throughput;
    GanttEntry gantt[MAX_GANTT];
    int gantt_len;
    Process procs[MAX_PROCESSES];
    int n;
} AlgoResult;

/* ---- CSV Input ---- */

int read_csv(const char *filename, Process procs[])
{
    FILE *f = fopen(filename, "r");
    if (!f) {
        fprintf(stderr, "Error: Cannot open %s\n", filename);
        return -1;
    }

    char line[256];
    int n = 0;

    /* Skip header */
    if (fgets(line, sizeof(line), f) == NULL) {
        fclose(f);
        return 0;
    }

    while (fgets(line, sizeof(line), f) && n < MAX_PROCESSES) {
        int pid, arr, burst, prio;
        if (sscanf(line, "%d,%d,%d,%d", &pid, &arr, &burst, &prio) == 4) {
            procs[n].pid = pid;
            procs[n].arrival_time = arr;
            procs[n].burst_time = burst;
            procs[n].priority = prio;
            procs[n].remaining_time = burst;
            procs[n].start_time = -1;
            procs[n].completion_time = 0;
            procs[n].waiting_time = 0;
            procs[n].turnaround_time = 0;
            procs[n].completed = false;
            n++;
        }
    }
    fclose(f);
    return n;
}

/* ---- Sort by arrival time (stable) ---- */

static int cmp_arrival(const void *a, const void *b)
{
    const Process *pa = (const Process *)a;
    const Process *pb = (const Process *)b;
    if (pa->arrival_time != pb->arrival_time)
        return pa->arrival_time - pb->arrival_time;
    return pa->pid - pb->pid;
}

/* ---- Compute Metrics ---- */

static void compute_metrics(AlgoResult *r)
{
    double total_wait = 0, total_tat = 0;
    int total_burst = 0;
    int max_completion = 0;
    int min_arrival = r->procs[0].arrival_time;

    for (int i = 0; i < r->n; i++) {
        total_wait += r->procs[i].waiting_time;
        total_tat += r->procs[i].turnaround_time;
        total_burst += r->procs[i].burst_time;
        if (r->procs[i].completion_time > max_completion)
            max_completion = r->procs[i].completion_time;
        if (r->procs[i].arrival_time < min_arrival)
            min_arrival = r->procs[i].arrival_time;
    }

    int span = max_completion - min_arrival;
    r->avg_wait = total_wait / r->n;
    r->avg_tat = total_tat / r->n;
    r->cpu_util = (span > 0) ? (100.0 * total_burst / span) : 100.0;
    r->throughput = (span > 0) ? ((double)r->n / span) : (double)r->n;
}

/* ---- ASCII Gantt Chart ---- */

static void print_gantt(AlgoResult *r)
{
    printf("\n  Gantt: ");
    for (int i = 0; i < r->gantt_len; i++)
        printf("|P%d", r->gantt[i].pid);
    printf("|\n");

    printf("         ");
    for (int i = 0; i < r->gantt_len; i++)
        printf("%-3d", r->gantt[i].start);
    if (r->gantt_len > 0)
        printf("%d", r->gantt[r->gantt_len - 1].end);
    printf("\n");
}

/* ---- FCFS ---- */

static void fcfs(Process orig[], int n, AlgoResult *r)
{
    strcpy(r->name, "FCFS");
    r->n = n;
    memcpy(r->procs, orig, sizeof(Process) * n);
    qsort(r->procs, n, sizeof(Process), cmp_arrival);
    r->gantt_len = 0;

    int t = 0;
    for (int i = 0; i < n; i++) {
        if (t < r->procs[i].arrival_time)
            t = r->procs[i].arrival_time;
        r->procs[i].start_time = t;
        r->procs[i].completion_time = t + r->procs[i].burst_time;
        r->procs[i].turnaround_time =
            r->procs[i].completion_time - r->procs[i].arrival_time;
        r->procs[i].waiting_time =
            r->procs[i].turnaround_time - r->procs[i].burst_time;

        r->gantt[r->gantt_len].pid = r->procs[i].pid;
        r->gantt[r->gantt_len].start = t;
        r->gantt[r->gantt_len].end = r->procs[i].completion_time;
        r->gantt_len++;

        t = r->procs[i].completion_time;
    }
    compute_metrics(r);
}

/* ---- SJF (non-preemptive) ---- */

static void sjf(Process orig[], int n, AlgoResult *r)
{
    strcpy(r->name, "SJF");
    r->n = n;
    memcpy(r->procs, orig, sizeof(Process) * n);
    qsort(r->procs, n, sizeof(Process), cmp_arrival);
    r->gantt_len = 0;

    for (int i = 0; i < n; i++)
        r->procs[i].completed = false;

    int t = 0, done = 0;
    while (done < n) {
        int best = -1, min_b = __INT_MAX__;
        for (int i = 0; i < n; i++) {
            if (!r->procs[i].completed &&
                r->procs[i].arrival_time <= t &&
                r->procs[i].burst_time < min_b) {
                min_b = r->procs[i].burst_time;
                best = i;
            }
        }
        if (best == -1) { t++; continue; }

        r->procs[best].start_time = t;
        r->procs[best].completion_time = t + r->procs[best].burst_time;
        r->procs[best].turnaround_time =
            r->procs[best].completion_time - r->procs[best].arrival_time;
        r->procs[best].waiting_time =
            r->procs[best].turnaround_time - r->procs[best].burst_time;
        r->procs[best].completed = true;

        r->gantt[r->gantt_len].pid = r->procs[best].pid;
        r->gantt[r->gantt_len].start = t;
        r->gantt[r->gantt_len].end = r->procs[best].completion_time;
        r->gantt_len++;

        t = r->procs[best].completion_time;
        done++;
    }
    compute_metrics(r);
}

/* ---- Round Robin (quantum = RR_QUANTUM) ---- */

static void rr(Process orig[], int n, AlgoResult *r)
{
    strcpy(r->name, "RR");
    r->n = n;
    memcpy(r->procs, orig, sizeof(Process) * n);
    qsort(r->procs, n, sizeof(Process), cmp_arrival);
    r->gantt_len = 0;

    for (int i = 0; i < n; i++) {
        r->procs[i].remaining_time = r->procs[i].burst_time;
        r->procs[i].start_time = -1;
        r->procs[i].completed = false;
    }

    int queue[MAX_GANTT], front = 0, rear = 0;
    bool in_queue[MAX_PROCESSES] = {false};
    int t = 0, done = 0;

    /* Enqueue processes arriving at time 0 */
    for (int i = 0; i < n; i++) {
        if (r->procs[i].arrival_time <= 0) {
            queue[rear++] = i;
            in_queue[i] = true;
        }
    }

    while (done < n) {
        if (front == rear) {
            t++;
            for (int i = 0; i < n; i++) {
                if (!r->procs[i].completed && !in_queue[i] &&
                    r->procs[i].arrival_time <= t) {
                    queue[rear++] = i;
                    in_queue[i] = true;
                }
            }
            continue;
        }

        int idx = queue[front++];
        in_queue[idx] = false;

        if (r->procs[idx].start_time == -1)
            r->procs[idx].start_time = t;

        int exec = (r->procs[idx].remaining_time < RR_QUANTUM)
                       ? r->procs[idx].remaining_time : RR_QUANTUM;

        r->gantt[r->gantt_len].pid = r->procs[idx].pid;
        r->gantt[r->gantt_len].start = t;
        r->gantt[r->gantt_len].end = t + exec;
        r->gantt_len++;

        t += exec;
        r->procs[idx].remaining_time -= exec;

        /* Enqueue new arrivals during this quantum */
        for (int i = 0; i < n; i++) {
            if (i != idx && !r->procs[i].completed && !in_queue[i] &&
                r->procs[i].arrival_time <= t &&
                r->procs[i].remaining_time > 0) {
                queue[rear++] = i;
                in_queue[i] = true;
            }
        }

        if (r->procs[idx].remaining_time > 0) {
            queue[rear++] = idx;
            in_queue[idx] = true;
        } else {
            r->procs[idx].completed = true;
            r->procs[idx].completion_time = t;
            r->procs[idx].turnaround_time =
                r->procs[idx].completion_time - r->procs[idx].arrival_time;
            r->procs[idx].waiting_time =
                r->procs[idx].turnaround_time - r->procs[idx].burst_time;
            done++;
        }
    }
    compute_metrics(r);
}

/* ---- Priority (preemptive) ---- */

static void priority_sched(Process orig[], int n, AlgoResult *r)
{
    strcpy(r->name, "Priority");
    r->n = n;
    memcpy(r->procs, orig, sizeof(Process) * n);
    qsort(r->procs, n, sizeof(Process), cmp_arrival);
    r->gantt_len = 0;

    for (int i = 0; i < n; i++) {
        r->procs[i].remaining_time = r->procs[i].burst_time;
        r->procs[i].start_time = -1;
        r->procs[i].completed = false;
    }

    int t = 0, done = 0, last_pid = -1, seg_start = 0;
    int max_time = 0;
    for (int i = 0; i < n; i++)
        max_time += r->procs[i].burst_time + r->procs[i].arrival_time;

    while (done < n && t <= max_time) {
        int best = -1, best_prio = __INT_MAX__;
        for (int i = 0; i < n; i++) {
            if (!r->procs[i].completed &&
                r->procs[i].arrival_time <= t &&
                r->procs[i].priority < best_prio) {
                best_prio = r->procs[i].priority;
                best = i;
            }
        }

        if (best == -1) { t++; continue; }

        if (r->procs[best].start_time == -1)
            r->procs[best].start_time = t;

        /* Track Gantt segments */
        if (r->procs[best].pid != last_pid) {
            if (last_pid != -1 && r->gantt_len < MAX_GANTT) {
                r->gantt[r->gantt_len].pid = last_pid;
                r->gantt[r->gantt_len].start = seg_start;
                r->gantt[r->gantt_len].end = t;
                r->gantt_len++;
            }
            last_pid = r->procs[best].pid;
            seg_start = t;
        }

        r->procs[best].remaining_time--;
        t++;

        if (r->procs[best].remaining_time == 0) {
            r->procs[best].completed = true;
            r->procs[best].completion_time = t;
            r->procs[best].turnaround_time =
                r->procs[best].completion_time - r->procs[best].arrival_time;
            r->procs[best].waiting_time =
                r->procs[best].turnaround_time - r->procs[best].burst_time;

            /* Close current Gantt segment */
            if (r->gantt_len < MAX_GANTT) {
                r->gantt[r->gantt_len].pid = last_pid;
                r->gantt[r->gantt_len].start = seg_start;
                r->gantt[r->gantt_len].end = t;
                r->gantt_len++;
            }
            last_pid = -1;
            done++;
        }
    }
    compute_metrics(r);
}

/* ---- Comparison Table ---- */

static void print_comparison(AlgoResult results[], int count)
{
    printf("\n============================================================\n");
    printf("%-10s | %10s | %10s | %6s | %10s\n",
           "Algorithm", "Avg Wait", "Avg TAT", "CPU%", "Throughput");
    printf("------------------------------------------------------------\n");
    for (int i = 0; i < count; i++) {
        printf("%-10s | %10.2f | %10.2f | %5.1f%% | %10.4f\n",
               results[i].name,
               results[i].avg_wait,
               results[i].avg_tat,
               results[i].cpu_util,
               results[i].throughput);
    }
    printf("============================================================\n");
}

/* ---- JSON Export ---- */

static void export_json(AlgoResult results[], int count,
                        const char *output_dir)
{
    char path[512];
    snprintf(path, sizeof(path), "%s/scheduler_results.json", output_dir);

    /* Create directory (best effort) */
    char cmd[600];
    snprintf(cmd, sizeof(cmd),
#ifdef _WIN32
             "if not exist \"%s\" mkdir \"%s\"",
#else
             "mkdir -p \"%s\" 2>/dev/null; echo ok > /dev/null",
#endif
             output_dir, output_dir);
    (void)system(cmd);

    FILE *f = fopen(path, "w");
    if (!f) {
        fprintf(stderr, "Warning: Cannot write %s\n", path);
        return;
    }

    fprintf(f, "[\n");
    for (int a = 0; a < count; a++) {
        AlgoResult *r = &results[a];
        fprintf(f, "  {\n");
        fprintf(f, "    \"algorithm\": \"%s\",\n", r->name);
        fprintf(f, "    \"metrics\": {\n");
        fprintf(f, "      \"avg_waiting_time\": %.2f,\n", r->avg_wait);
        fprintf(f, "      \"avg_turnaround_time\": %.2f,\n", r->avg_tat);
        fprintf(f, "      \"cpu_utilization\": %.1f,\n", r->cpu_util);
        fprintf(f, "      \"throughput\": %.4f\n", r->throughput);
        fprintf(f, "    },\n");
        fprintf(f, "    \"processes\": [\n");
        for (int i = 0; i < r->n; i++) {
            fprintf(f, "      {\"pid\": %d, \"arrival\": %d, \"burst\": %d, "
                       "\"priority\": %d, \"start\": %d, \"completion\": %d, "
                       "\"waiting\": %d, \"turnaround\": %d}%s\n",
                    r->procs[i].pid,
                    r->procs[i].arrival_time,
                    r->procs[i].burst_time,
                    r->procs[i].priority,
                    r->procs[i].start_time,
                    r->procs[i].completion_time,
                    r->procs[i].waiting_time,
                    r->procs[i].turnaround_time,
                    (i < r->n - 1) ? "," : "");
        }
        fprintf(f, "    ]\n");
        fprintf(f, "  }%s\n", (a < count - 1) ? "," : "");
    }
    fprintf(f, "]\n");
    fclose(f);

    printf("\nResults exported to %s\n", path);
}

/* ---- Usage ---- */

static void usage(const char *prog)
{
    fprintf(stderr,
        "Usage: %s --algo <fcfs|sjf|rr|priority|all> --input <file.csv>\n",
        prog);
}

/* ---- Main ---- */

int main(int argc, char *argv[])
{
    const char *algo = "all";
    const char *input_file = NULL;

    /* Parse CLI args */
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--algo") == 0 && i + 1 < argc) {
            algo = argv[++i];
        } else if (strcmp(argv[i], "--input") == 0 && i + 1 < argc) {
            input_file = argv[++i];
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            usage(argv[0]);
            return 0;
        }
    }

    Process procs[MAX_PROCESSES];
    int n;

    if (input_file) {
        n = read_csv(input_file, procs);
        if (n <= 0) {
            fprintf(stderr, "Error: No valid processes in %s\n", input_file);
            return 1;
        }
    } else {
        /* Default sample workload */
        Process defaults[] = {
            {.pid=1, .arrival_time=0, .burst_time=8,  .priority=3},
            {.pid=2, .arrival_time=1, .burst_time=4,  .priority=1},
            {.pid=3, .arrival_time=2, .burst_time=9,  .priority=4},
            {.pid=4, .arrival_time=3, .burst_time=5,  .priority=2},
            {.pid=5, .arrival_time=4, .burst_time=2,  .priority=5},
        };
        n = 5;
        memcpy(procs, defaults, sizeof(defaults));
    }

    /* Sort input by arrival time */
    qsort(procs, n, sizeof(Process), cmp_arrival);

    printf("Eonix OS — Scheduler Simulator\n");
    printf("================================\n");
    printf("Processes: %d | Algorithm: %s\n", n, algo);

    AlgoResult results[4];
    int rcount = 0;

    bool run_fcfs = (strcmp(algo, "fcfs") == 0 || strcmp(algo, "all") == 0);
    bool run_sjf  = (strcmp(algo, "sjf")  == 0 || strcmp(algo, "all") == 0);
    bool run_rr   = (strcmp(algo, "rr")   == 0 || strcmp(algo, "all") == 0);
    bool run_pri  = (strcmp(algo, "priority") == 0 || strcmp(algo, "all") == 0);

    if (run_fcfs) {
        fcfs(procs, n, &results[rcount]);
        printf("\n=== FCFS Scheduling ===");
        print_gantt(&results[rcount]);
        rcount++;
    }
    if (run_sjf) {
        sjf(procs, n, &results[rcount]);
        printf("\n=== SJF Scheduling ===");
        print_gantt(&results[rcount]);
        rcount++;
    }
    if (run_rr) {
        rr(procs, n, &results[rcount]);
        printf("\n=== Round Robin (Q=%d) ===", RR_QUANTUM);
        print_gantt(&results[rcount]);
        rcount++;
    }
    if (run_pri) {
        priority_sched(procs, n, &results[rcount]);
        printf("\n=== Priority (Preemptive) ===");
        print_gantt(&results[rcount]);
        rcount++;
    }

    if (rcount == 0) {
        fprintf(stderr, "Error: Unknown algorithm '%s'\n", algo);
        usage(argv[0]);
        return 1;
    }

    if (rcount > 1)
        print_comparison(results, rcount);

    export_json(results, rcount, "results");

    return 0;
}
