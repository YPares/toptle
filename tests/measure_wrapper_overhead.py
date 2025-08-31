#!/usr/bin/env python3
"""
Accurate measurement of wrapper process overhead
"""

import subprocess
import time
import psutil
import os
import signal

def measure_process_overhead(command, duration=10):
    """Measure CPU and memory overhead of a process"""
    print(f"Testing: {' '.join(command)}")
    
    # Start the process
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Give it time to start up
    time.sleep(1)
    
    try:
        # Get psutil process handle
        ps_process = psutil.Process(process.pid)
        
        cpu_samples = []
        memory_samples = []
        
        print("Sampling every 1s:")
        start_time = time.time()
        
        while time.time() - start_time < duration:
            try:
                # Get CPU percentage
                cpu = ps_process.cpu_percent(interval=0.1)  # Non-blocking
                
                # Get memory info
                memory_info = ps_process.memory_info()
                memory_mb = memory_info.rss / (1024 * 1024)
                
                cpu_samples.append(cpu)
                memory_samples.append(memory_mb)
                
                print(f"  CPU: {cpu:5.1f}%, RAM: {memory_mb:6.1f}MB")
                
                time.sleep(1)
                
            except psutil.NoSuchProcess:
                print("  Process finished")
                break
                
        # Calculate statistics
        if cpu_samples:
            avg_cpu = sum(cpu_samples) / len(cpu_samples)
            max_cpu = max(cpu_samples)
            avg_memory = sum(memory_samples) / len(memory_samples)
            max_memory = max(memory_samples)
            
            result = {
                'avg_cpu': avg_cpu,
                'max_cpu': max_cpu,
                'avg_memory': avg_memory,
                'max_memory': max_memory,
                'samples': len(cpu_samples)
            }
        else:
            result = {'error': 'No samples collected'}
            
    except Exception as e:
        result = {'error': str(e)}
    
    finally:
        # Clean up
        try:
            process.terminate()
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    
    return result

def main():
    print("Process Monitor Wrapper Overhead Test")
    print("=" * 45)
    
    tests = [
        (["../toptle.py", "--interval", "2", "--", "sleep", "20"], "Python Wrapper (2s)"),
        (["../toptle.py", "--interval", "0.5", "--", "sleep", "20"], "Python Wrapper (0.5s)"),
        (["./process_monitor_wrapper.sh", "sleep", "20"], "Bash Wrapper"),
        (["sleep", "20"], "Baseline (sleep only)")
    ]
    
    results = []
    
    for cmd, name in tests:
        print(f"\n{name}:")
        print("-" * (len(name) + 1))
        
        result = measure_process_overhead(cmd, duration=8)
        results.append((name, result))
        
        if 'error' not in result:
            print(f"Summary - Avg CPU: {result['avg_cpu']:.1f}%, Avg RAM: {result['avg_memory']:.1f}MB")
        else:
            print(f"Error: {result['error']}")
    
    # Summary table
    print(f"\n{'=' * 60}")
    print("PERFORMANCE SUMMARY")
    print(f"{'=' * 60}")
    print(f"{'Test':<20} {'Avg CPU%':<10} {'Max CPU%':<10} {'Avg RAM MB':<12}")
    print("-" * 60)
    
    for name, result in results:
        if 'error' not in result:
            print(f"{name:<20} {result['avg_cpu']:<10.1f} {result['max_cpu']:<10.1f} {result['avg_memory']:<12.1f}")
        else:
            print(f"{name:<20} ERROR")
    
    # Analysis
    print(f"\n{'ANALYSIS:'}")
    baseline = None
    python_2s = None
    
    for name, result in results:
        if 'Baseline' in name and 'error' not in result:
            baseline = result
        elif 'Python Wrapper (2s)' in name and 'error' not in result:
            python_2s = result
    
    if baseline and python_2s:
        cpu_overhead = python_2s['avg_cpu'] - baseline['avg_cpu']
        ram_overhead = python_2s['avg_memory'] - baseline['avg_memory']
        print(f"Python wrapper overhead: +{cpu_overhead:.1f}% CPU, +{ram_overhead:.1f}MB RAM")
        
        if cpu_overhead < 5.0 and ram_overhead < 50.0:
            print("✅ Overhead is acceptable")
        elif cpu_overhead < 10.0 and ram_overhead < 100.0:
            print("⚠️  Overhead is moderate")
        else:
            print("❌ Overhead is high - consider optimization")

if __name__ == "__main__":
    main()
