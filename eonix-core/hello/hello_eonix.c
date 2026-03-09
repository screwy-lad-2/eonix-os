#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
MODULE_LICENSE("GPL");
MODULE_AUTHOR("Eonix OS");
MODULE_DESCRIPTION("Eonix QEMU test module");
static int __init hello_init(void) {
    printk(KERN_INFO "EONIX: Kernel module loaded\n");
    return 0;
}
static void __exit hello_exit(void) {
    printk(KERN_INFO "EONIX: Kernel module unloaded\n");
}
module_init(hello_init);
module_exit(hello_exit);
