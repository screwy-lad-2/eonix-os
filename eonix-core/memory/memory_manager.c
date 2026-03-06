/*
 * Eonix OS — Adaptive Memory Manager
 * ====================================
 * Hybrid LRU-K + ML-predicted page replacement.
 * Eviction score = (0.6 × LRU-K recency) + (0.4 × ML access prediction)
 *
 * This is a userspace simulator. The kernel module version will
 * hook into Linux memory management subsystem.
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>

#define MAX_PAGES       1024
#define K_VALUE         2       /* LRU-K: track last K references */
#define MAX_HISTORY     16      /* Max reference history per page */

typedef struct {
    int page_id;
    bool present;             /* Is page in physical memory? */
    int ref_history[MAX_HISTORY];
    int ref_count;
    double ml_access_prob;    /* ML-predicted probability of access in next 10s */
} PageEntry;

typedef struct {
    PageEntry pages[MAX_PAGES];
    int page_count;
    int frame_count;          /* Physical memory frames available */
    int frames_used;
    int page_faults;
    int time_tick;
} MemoryManager;

/* Calculate LRU-K recency score (lower = less recently used) */
static double lruk_score(PageEntry *page, int current_time)
{
    if (page->ref_count == 0)
        return 0.0;

    /* K-th most recent reference */
    int k_ref;
    if (page->ref_count >= K_VALUE)
        k_ref = page->ref_history[page->ref_count - K_VALUE];
    else
        k_ref = page->ref_history[0];

    /* Normalize to 0-1 range based on recency */
    double age = (double)(current_time - k_ref);
    return 1.0 / (1.0 + age);
}

/* Combined eviction score: higher = more likely to be needed */
static double eviction_score(PageEntry *page, int current_time)
{
    double recency = lruk_score(page, current_time);
    return (0.6 * recency) + (0.4 * page->ml_access_prob);
}

/* Find page with lowest eviction score (best candidate to evict) */
static int find_victim(MemoryManager *mm)
{
    int victim = -1;
    double min_score = 2.0;

    for (int i = 0; i < mm->page_count; i++) {
        if (mm->pages[i].present) {
            double score = eviction_score(&mm->pages[i], mm->time_tick);
            if (score < min_score) {
                min_score = score;
                victim = i;
            }
        }
    }
    return victim;
}

/* Access a page */
void access_page(MemoryManager *mm, int page_id)
{
    mm->time_tick++;

    /* Find page in table */
    PageEntry *page = NULL;
    for (int i = 0; i < mm->page_count; i++) {
        if (mm->pages[i].page_id == page_id) {
            page = &mm->pages[i];
            break;
        }
    }

    /* New page? Add to table */
    if (!page && mm->page_count < MAX_PAGES) {
        page = &mm->pages[mm->page_count++];
        page->page_id = page_id;
        page->present = false;
        page->ref_count = 0;
        page->ml_access_prob = 0.5; /* Default prediction */
    }

    if (!page)
        return;

    /* Record reference */
    if (page->ref_count < MAX_HISTORY)
        page->ref_history[page->ref_count++] = mm->time_tick;

    /* Page fault? */
    if (!page->present) {
        mm->page_faults++;

        if (mm->frames_used >= mm->frame_count) {
            /* Evict victim */
            int victim = find_victim(mm);
            if (victim >= 0) {
                mm->pages[victim].present = false;
                mm->frames_used--;
            }
        }

        page->present = true;
        mm->frames_used++;
    }
}

int main(void)
{
    MemoryManager mm = {0};
    mm.frame_count = 4; /* Simulate 4 physical frames */

    /* Simulate a page reference string */
    int refs[] = {1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5};
    int n = sizeof(refs) / sizeof(refs[0]);

    printf("Eonix OS — Adaptive Memory Manager Simulator\n");
    printf("=============================================\n");
    printf("Physical frames: %d\n", mm.frame_count);
    printf("Page references: ");
    for (int i = 0; i < n; i++)
        printf("%d ", refs[i]);
    printf("\n\n");

    for (int i = 0; i < n; i++) {
        int prev_faults = mm.page_faults;
        access_page(&mm, refs[i]);
        printf("Access page %d: %s (total faults: %d)\n",
               refs[i],
               mm.page_faults > prev_faults ? "FAULT" : "HIT",
               mm.page_faults);
    }

    printf("\nTotal page faults: %d / %d accesses\n", mm.page_faults, n);
    printf("Hit rate: %.1f%%\n",
           100.0 * (n - mm.page_faults) / n);

    return 0;
}
