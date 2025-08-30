#!/usr/bin/env python3
"""
Debug CPU usage issue by isolating components
"""

import subprocess
import time
import psutil
import select
import sys
import os
import pty

def test_baseline_pty():
    """Test just PTY forwarding without monitoring"""
    print("Testing baseline PTY forwarding...")
    
    master_fd, slave_fd = pty.openpty()
    
    process = subprocess.Popen(
        ["sleep", "10"],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        preexec_fn=os.setsid
    )
    
    os.close(slave_fd)
    
    try:
        # Simple I/O forwarding loop
        start_time = time.time()
        while time.time() - start_time < 8:
            ready, _, _ = select.select([sys.stdin, master_fd], [], [], 1.0)
            
            if sys.stdin in ready:
                try:
                    data = os.read(sys.stdin.fileno(), 1024)
                    if data:
                        os.write(master_fd, data)
                except OSError:
                    break
            
            if master_fd in ready:
                try:
                    data = os.read(master_fd, 1024)
                    if data:
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()
                    else:
                        break
                except OSError:
                    break
            
            # Check if process finished
            if process.poll() is not None:
                break
    
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass
        process.terminate()
        process.wait()

def test_psutil_overhead():
    """Test just psutil monitoring without PTY"""
    print("Testing psutil monitoring overhead...")
    
    # Start a simple process
    process = subprocess.Popen(["sleep", "10"])
    ps_process = psutil.Process(process.pid)
    
    try:
        start_time = time.time()
        while time.time() - start_time < 8:
            # This is what our monitoring thread does
            try:
                if ps_process.is_running():
                    processes = [ps_process] + ps_process.children(recursive=True)
                    
                    total_cpu = 0.0
                    total_memory = 0.0
                    
                    for proc in processes:
                        try:
                            cpu_percent = proc.cpu_percent()
                            memory_info = proc.memory_info()
                            memory_mb = memory_info.rss / (1024 * 1024)
                            
                            total_cpu += cpu_percent
                            total_memory += memory_mb
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    
                    stats = f"{total_cpu:.1f}% CPU, {total_memory:.1f}MB RAM"
                    print(f"Stats: {stats}")
                else:
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            
            time.sleep(2.0)  # Our monitoring interval
    
    finally:
        process.terminate()
        process.wait()

def measure_component(test_func, name):
    """Measure CPU usage of a test function"""
    print(f"\n=== {name} ===")
    
    # Start the test in a subprocess so we can measure it
    import multiprocessing
    
    def run_test():
        test_func()
    
    process = multiprocessing.Process(target=run_test)
    process.start()
    
    # Give it time to start
    time.sleep(1)
    
    try:
        ps_process = psutil.Process(process.pid)
        
        samples = []
        for i in range(6):  # 6 seconds of sampling
            try:
                cpu = ps_process.cpu_percent(interval=1)
                memory_mb = ps_process.memory_info().rss / (1024 * 1024)
                samples.append((cpu, memory_mb))
                print(f"Sample {i+1}: {cpu:.1f}% CPU, {memory_mb:.1f}MB RAM")
            except psutil.NoSuchProcess:
                break
        
        if samples:
            avg_cpu = sum(s[0] for s in samples) / len(samples)
            avg_mem = sum(s[1] for s in samples) / len(samples)
            print(f"Average: {avg_cpu:.1f}% CPU, {avg_mem:.1f}MB RAM")
        
    finally:
        process.terminate()
        process.join()

if __name__ == "__main__":
    print("Debugging CPU usage in process monitor components")
    print("=" * 50)
    
    measure_component(test_baseline_pty, "Baseline PTY Forwarding")
    measure_component(test_psutil_overhead, "PSUtil Monitoring Only")