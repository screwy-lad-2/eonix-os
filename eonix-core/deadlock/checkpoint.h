/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _EONIX_CHECKPOINT_H
#define _EONIX_CHECKPOINT_H

#include <linux/types.h>
#include <linux/sched.h>
#include <linux/seq_file.h>

#define MAX_CHECKPOINTS   64
#define CHECKPOINT_MAGIC  0xE0010001

struct eonix_checkpoint {
	u32   magic;
	pid_t pid;
	char  comm[TASK_COMM_LEN];
	u64   timestamp_ns;
	int   exit_code;
	int   held_resources[16];
	int   held_count;
	int   waiting_for;
	uid_t uid;
	gid_t gid;
	char  exe_path[256];
	char  cmdline[512];
	bool  valid;
};

int  eonix_checkpoint_save(pid_t pid, const int *held, int held_count,
			   int waiting_for);
struct eonix_checkpoint *eonix_checkpoint_get(pid_t pid);
void eonix_checkpoint_clear(pid_t pid);
int  eonix_checkpoints_show(struct seq_file *m, void *v);
void eonix_checkpoint_init(void);

#endif /* _EONIX_CHECKPOINT_H */
