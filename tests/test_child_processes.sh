#!/bin/bash
echo "=== Testing Process Tree Monitoring ==="
echo "Parent PID: $$"

# Create a Python script that spawns actual child processes
# This ensures they're direct children that our process tree detection will find
python3 -c "
import time
import multiprocessing
import tempfile
import os
import sys

def cpu_intensive_work():
    print('CPU child starting intensive computation...', flush=True)
    start = time.time()
    while time.time() - start < 8:
        # CPU-intensive work
        sum(i*i for i in range(10000))
    print('CPU child finished', flush=True)

def disk_io_work():
    print('Disk child starting I/O operations...', flush=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(8):
            # Write and read 5MB files
            filepath = os.path.join(tmpdir, f'test_{i}.dat')
            with open(filepath, 'wb') as f:
                f.write(b'x' * 5000000)  # Write 5MB
            with open(filepath, 'rb') as f:
                _ = f.read()  # Read it back
            print(f'Disk I/O iteration {i+1}/8 (5MB write+read)', flush=True)
            time.sleep(1)
    print('Disk child finished', flush=True)

def memory_intensive_work():
    print('Memory child starting allocation...', flush=True)
    data = []
    for i in range(10):
        data.append('x' * 10000000)  # 10MB chunks
        print(f'Allocated {(i+1)*10}MB', flush=True)
        time.sleep(1)
    print('Memory child finished', flush=True)

if __name__ == '__main__':
    # Start all processes
    cpu_process = multiprocessing.Process(target=cpu_intensive_work)
    disk_process = multiprocessing.Process(target=disk_io_work)
    memory_process = multiprocessing.Process(target=memory_intensive_work)
    
    cpu_process.start()
    disk_process.start()
    memory_process.start()
    
    # Wait and show progress
    for i in range(1, 11):
        print(f'Parent iteration {i}/10', flush=True)
        time.sleep(1)
    
    # Wait for children
    cpu_process.join()
    disk_process.join()
    memory_process.join()
    
    print('=== All processes finished ===', flush=True)
"