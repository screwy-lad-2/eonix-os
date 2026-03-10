#!/bin/bash
set -e

# Restore symlink
sudo ln -sf /usr/src/wsl2-kernel "/lib/modules/$(uname -r)/build"

# Prepare build dir
rm -rf /tmp/eonix_verify
mkdir -p /tmp/eonix_verify/tests
cp /mnt/c/Users/laska/Projects/eonix-os/eonix-core/deadlock/rag_monitor.c /tmp/eonix_verify/
cp /mnt/c/Users/laska/Projects/eonix-os/eonix-core/deadlock/Makefile /tmp/eonix_verify/
cp /mnt/c/Users/laska/Projects/eonix-os/eonix-core/deadlock/tests/*.c /tmp/eonix_verify/tests/
cp /mnt/c/Users/laska/Projects/eonix-os/eonix-core/deadlock/tests/benchmark.sh /tmp/eonix_verify/tests/

cd /tmp/eonix_verify

echo "=== BUILD ==="
make 2>&1 | tail -5
echo "BUILD_RC=$?"

echo "=== MODULE SIZE ==="
ls -la eonix_deadlock.ko

echo "=== BUILD TESTS ==="
gcc -O2 -Wall -pthread -o tests/trigger_deadlock tests/trigger_deadlock.c && echo "trigger_deadlock: OK"
gcc -O2 -Wall -pthread -o tests/trigger_deadlock_3way tests/trigger_deadlock_3way.c && echo "trigger_3way: OK"

echo "=== UNLOAD OLD ==="
sudo rmmod eonix_deadlock 2>/dev/null || true

echo "=== LOAD MODULE ==="
sudo insmod eonix_deadlock.ko
sleep 1

echo "=== LSMOD ==="
lsmod | grep eonix

echo "=== DMESG INIT (5 messages expected) ==="
dmesg | grep "EONIX_RAG" | tail -5

echo "=== /proc/eonix/ ==="
ls -la /proc/eonix/

echo "=== DEADLOCK_LOG (initial) ==="
cat /proc/eonix/deadlock_log

echo "=== RAG_STATE (initial) ==="
cat /proc/eonix/rag_state

echo "=========================================="
echo "=== RUN 2-WAY TRIGGER TEST ==="
echo "=========================================="
sudo tests/trigger_deadlock
echo "2WAY_RC=$?"

echo "=========================================="
echo "=== RUN 3-WAY TRIGGER TEST ==="
echo "=========================================="
sudo tests/trigger_deadlock_3way
echo "3WAY_RC=$?"

echo "=========================================="
echo "=== RUN BENCHMARK (5 iterations) ==="
echo "=========================================="
sudo bash tests/benchmark.sh 5
echo "BENCH_RC=$?"

echo "=== SAVING BENCHMARK ==="
mkdir -p /mnt/c/Users/laska/Projects/eonix-os/results
sudo bash tests/benchmark.sh 10 | tee /mnt/c/Users/laska/Projects/eonix-os/results/deadlock_benchmark.txt
echo "SAVED=$?"

echo "=== FINAL DMESG ==="
dmesg | grep "EONIX_RAG" | tail -10

echo "=== UNLOAD ==="
sudo rmmod eonix_deadlock
echo "UNLOADED"
dmesg | grep "EONIX_RAG" | tail -3

echo "=== VERIFICATION COMPLETE ==="
