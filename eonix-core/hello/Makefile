obj-m += hello_eonix.o
KBUILD_MODPOST_WARN := 1

KDIR := /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

all:
	$(MAKE) KBUILD_MODPOST_WARN=1 -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

test: all
	sudo insmod hello_eonix.ko
	@sleep 1
	sudo dmesg | grep -i eonix | tail -3
	sudo rmmod hello_eonix
	sudo dmesg | grep -i eonix | tail -3

.PHONY: all clean test
