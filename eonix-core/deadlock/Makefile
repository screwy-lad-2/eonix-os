obj-m += eonix_deadlock.o
eonix_deadlock-objs := rag_monitor.o
KBUILD_MODPOST_WARN := 1

KDIR := /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

all:
	$(MAKE) KBUILD_MODPOST_WARN=1 -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean
	rm -f tests/trigger_deadlock tests/trigger_deadlock_3way

tests/trigger_deadlock: tests/trigger_deadlock.c
	gcc -O2 -Wall -pthread -o $@ $<

tests/trigger_deadlock_3way: tests/trigger_deadlock_3way.c
	gcc -O2 -Wall -pthread -o $@ $<

test: all
	@echo "=== Eonix Deadlock Module Test ==="
	@echo "[1] Loading module..."
	sudo insmod eonix_deadlock.ko
	@sleep 1
	@echo "[2] Checking /proc/eonix/deadlock_log:"
	cat /proc/eonix/deadlock_log
	@echo "[3] Checking /proc/eonix/rag_state:"
	cat /proc/eonix/rag_state
	@echo "[4] Inject 2-way deadlock via rag_inject..."
	sudo sh -c 'echo "HOLD 1001 10" > /proc/eonix/rag_inject'
	sudo sh -c 'echo "HOLD 1002 20" > /proc/eonix/rag_inject'
	sudo sh -c 'echo "WAIT 1001 20" > /proc/eonix/rag_inject'
	sudo sh -c 'echo "WAIT 1002 10" > /proc/eonix/rag_inject'
	@echo "[5] Waiting for detection cycle..."
	@sleep 2
	@echo "[6] Checking deadlock_log after injection:"
	cat /proc/eonix/deadlock_log
	@echo "[7] Unloading module..."
	sudo rmmod eonix_deadlock
	@echo "=== DONE ==="

.PHONY: all clean test
