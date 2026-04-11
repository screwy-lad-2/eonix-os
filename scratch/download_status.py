import os
import time
import sys

TARGET_DIR = r"c:\Users\laska\Desktop\Eonix OS\iso_out"
TARGET_FILE = os.path.join(TARGET_DIR, "eonix-os-0.9.0.iso")
EXPECTED_SIZE_GB = 6.45 # roughly 6929556088 bytes

def get_dir_size(path):
    total = 0
    try:
        if not os.path.exists(path):
            return 0
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_dir_size(entry.path)
    except Exception:
        pass
    return total

print(f"Monitoring download in {TARGET_DIR}...")
start_time = time.time()
last_size = 0

try:
    while True:
        current_size = get_dir_size(TARGET_DIR)
        elapsed = time.time() - start_time
        
        size_mb = current_size / (1024 * 1024)
        size_gb = current_size / (1024 * 1024 * 1024)
        
        speed = (current_size - last_size) / 5 if elapsed > 0 else 0
        speed_mb = speed / (1024 * 1024)
        
        progress = (size_gb / EXPECTED_SIZE_GB) * 100 if EXPECTED_SIZE_GB > 0 else 0
        
        print(f"\rProgress: {size_gb:.2f} GB / {EXPECTED_SIZE_GB:.2f} GB ({progress:.1f}%) | Speed: {speed_mb:.2f} MB/s | Elapsed: {int(elapsed)}s", end="")
        
        last_size = current_size
        time.sleep(5)
except KeyboardInterrupt:
    print("\nMonitor stopped.")
