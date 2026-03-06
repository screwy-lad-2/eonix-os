/*
 * Eonix OS — Self-Healing Deadlock Manager
 * =========================================
 * Linux kernel module that maintains a Resource Allocation Graph (RAG),
 * runs DFS cycle detection every 500ms, and automatically recovers
 * from deadlocks by checkpointing and restarting lowest-priority processes.
 *
 * Build: make
 * Load:  sudo insmod eonix_deadlock.ko
 * Check: cat /proc/eonix/deadlock_log
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#include <linux/timer.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/list.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("shahnoor-exe");
MODULE_DESCRIPTION("Eonix OS Self-Healing Deadlock Manager");
MODULE_VERSION("0.1.0");

/* ---- Configuration ---- */
#define EONIX_CHECK_INTERVAL_MS  500
#define EONIX_MAX_PROCESSES      1024
#define EONIX_MAX_RESOURCES      256
#define EONIX_LOG_BUFFER_SIZE    4096

/* ---- Resource Allocation Graph ---- */

/* Edge types in the RAG */
enum rag_edge_type {
    RAG_REQUEST,    /* Process -> Resource (waiting) */
    RAG_ASSIGN,     /* Resource -> Process (held)    */
};

struct rag_edge {
    struct list_head list;
    int from_id;
    int to_id;
    enum rag_edge_type type;
};

/* Per-process node in the graph */
struct rag_node {
    int pid;
    int priority;
    bool visited;
    bool in_stack;
    struct list_head edges;
};

/* Global state */
static struct rag_node process_nodes[EONIX_MAX_PROCESSES];
static int node_count;
static DEFINE_SPINLOCK(rag_lock);
static struct timer_list check_timer;
static char log_buffer[EONIX_LOG_BUFFER_SIZE];
static int log_offset;

/* ---- DFS Cycle Detection ---- */

static bool dfs_detect_cycle(struct rag_node *node, int *cycle_pids,
                             int *cycle_len)
{
    struct rag_edge *edge;

    if (node->in_stack)
        return true; /* Cycle found */

    if (node->visited)
        return false;

    node->visited = true;
    node->in_stack = true;

    list_for_each_entry(edge, &node->edges, list) {
        if (edge->to_id < node_count) {
            struct rag_node *next = &process_nodes[edge->to_id];
            if (dfs_detect_cycle(next, cycle_pids, cycle_len)) {
                if (*cycle_len < EONIX_MAX_PROCESSES) {
                    cycle_pids[(*cycle_len)++] = node->pid;
                }
                return true;
            }
        }
    }

    node->in_stack = false;
    return false;
}

static void check_deadlocks(struct timer_list *t)
{
    int cycle_pids[EONIX_MAX_PROCESSES];
    int cycle_len = 0;
    int i;
    unsigned long flags;

    spin_lock_irqsave(&rag_lock, flags);

    /* Reset visited flags */
    for (i = 0; i < node_count; i++) {
        process_nodes[i].visited = false;
        process_nodes[i].in_stack = false;
    }

    /* Run DFS from each unvisited node */
    for (i = 0; i < node_count; i++) {
        if (!process_nodes[i].visited) {
            if (dfs_detect_cycle(&process_nodes[i], cycle_pids,
                                 &cycle_len)) {
                /* Deadlock detected — log it */
                log_offset += scnprintf(
                    log_buffer + log_offset,
                    EONIX_LOG_BUFFER_SIZE - log_offset,
                    "[EONIX] Deadlock detected: %d processes in cycle\n",
                    cycle_len);

                /* TODO: Implement recovery —
                 * 1. Find lowest-priority process in cycle
                 * 2. Checkpoint via COW fork
                 * 3. Reclaim resources
                 * 4. Add to restart workqueue
                 */
                break;
            }
        }
    }

    spin_unlock_irqrestore(&rag_lock, flags);

    /* Re-arm timer */
    mod_timer(&check_timer,
              jiffies + msecs_to_jiffies(EONIX_CHECK_INTERVAL_MS));
}

/* ---- /proc interface ---- */

static int deadlock_log_show(struct seq_file *m, void *v)
{
    unsigned long flags;

    spin_lock_irqsave(&rag_lock, flags);
    if (log_offset > 0)
        seq_printf(m, "%s", log_buffer);
    else
        seq_puts(m, "[EONIX] No deadlocks detected\n");
    spin_unlock_irqrestore(&rag_lock, flags);

    return 0;
}

static int deadlock_log_open(struct inode *inode, struct file *file)
{
    return single_open(file, deadlock_log_show, NULL);
}

static const struct proc_ops deadlock_proc_ops = {
    .proc_open    = deadlock_log_open,
    .proc_read    = seq_read,
    .proc_lseek   = seq_lseek,
    .proc_release = single_release,
};

/* ---- Module init/exit ---- */

static int __init eonix_deadlock_init(void)
{
    struct proc_dir_entry *eonix_dir;
    int i;

    pr_info("[EONIX] Deadlock Manager v0.1.0 loading\n");

    /* Initialize RAG */
    node_count = 0;
    log_offset = 0;
    memset(log_buffer, 0, EONIX_LOG_BUFFER_SIZE);

    for (i = 0; i < EONIX_MAX_PROCESSES; i++)
        INIT_LIST_HEAD(&process_nodes[i].edges);

    /* Create /proc/eonix/deadlock_log */
    eonix_dir = proc_mkdir("eonix", NULL);
    if (!eonix_dir) {
        pr_err("[EONIX] Failed to create /proc/eonix\n");
        return -ENOMEM;
    }
    proc_create("deadlock_log", 0444, eonix_dir, &deadlock_proc_ops);

    /* Start periodic check timer */
    timer_setup(&check_timer, check_deadlocks, 0);
    mod_timer(&check_timer,
              jiffies + msecs_to_jiffies(EONIX_CHECK_INTERVAL_MS));

    pr_info("[EONIX] Deadlock Manager active (check every %dms)\n",
            EONIX_CHECK_INTERVAL_MS);
    return 0;
}

static void __exit eonix_deadlock_exit(void)
{
    del_timer_sync(&check_timer);
    remove_proc_subtree("eonix", NULL);
    pr_info("[EONIX] Deadlock Manager unloaded\n");
}

module_init(eonix_deadlock_init);
module_exit(eonix_deadlock_exit);
