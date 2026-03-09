obj-m += eonix_deadlock.o
eonix_deadlock-objs := rag_monitor.o
KBUILD_MODPOST_WARN := 1

KDIR := /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

all:
	$(MAKE) KBUILD_MODPOST_WARN=1 -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

test:
	@echo "Loading module..."
	sudo insmod eonix_deadlock.ko
	@sleep 1
	@echo "Checking /proc/eonix/deadlock_log:"
	cat /proc/eonix/deadlock_log
	@echo "Unloading module..."
	sudo rmmod eonix_deadlock

.PHONY: all clean test
