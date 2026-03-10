# Eonix OS — eBPF Syscall Security Monitor
# Build: make          (builds BPF object + userspace loader)
# Clean: make clean
# Requires: clang, llvm, libbpf-dev, linux-tools-common (for bpftool)

CLANG    ?= clang
GCC      ?= gcc
BPFTOOL  ?= bpftool
ARCH     := $(shell uname -m | sed 's/x86_64/x86/' | sed 's/aarch64/arm64/')

BPF_SRC  := syscall_monitor.bpf.c
BPF_OBJ  := syscall_monitor.bpf.o
VMLINUX  := vmlinux.h
USER_SRC := syscall_monitor.c
USER_BIN := syscall_monitor

CFLAGS   := -O2 -Wall -Wextra
BPF_CFLAGS := -O2 -g -target bpf -D__TARGET_ARCH_$(ARCH)

LDLIBS   := -lbpf -lelf -lz

.PHONY: all clean vmlinux

all: $(BPF_OBJ) $(USER_BIN)

# Generate vmlinux.h from running kernel's BTF if not present
$(VMLINUX):
	$(BPFTOOL) btf dump file /sys/kernel/btf/vmlinux format c > $@

$(BPF_OBJ): $(BPF_SRC) $(VMLINUX) syscall_monitor.h
	$(CLANG) $(BPF_CFLAGS) -c $< -o $@

$(USER_BIN): $(USER_SRC) syscall_monitor.h
	$(GCC) $(CFLAGS) -o $@ $< $(LDLIBS)

clean:
	rm -f $(BPF_OBJ) $(USER_BIN) $(VMLINUX)
