#!/usr/bin/env python3
"""
Performance test for process monitor wrappers
Tests CPU and memory overhead of the wrappers themselves
"""

import subprocess
import time
import psutil
import os
import sys
import threading
import statistics


def get_process_stats(pid):
    """Get CPU and memory stats for a specific process"""
    try:
        proc = psutil.Process(pid)
        return {
            "cpu_percent": proc.cpu_percent(),
            "memory_mb": proc.memory_info().rss / (1024 * 1024),
            "children_count": len(proc.children(recursive=True)),
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def monitor_process_overhead(command, duration=30, sample_interval=0.5):
    """Monitor the overhead of a wrapper process"""
    print(f"Testing command: {' '.join(command)}")
    print(f"Duration: {duration}s, Sample interval: {sample_interval}s")

    # Start the process
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    # Give process time to start
    time.sleep(1)

    cpu_samples = []
    memory_samples = []
    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            stats = get_process_stats(process.pid)
            if stats:
                cpu_samples.append(stats["cpu_percent"])
                memory_samples.append(stats["memory_mb"])
                print(
                    f"Sample: CPU {stats['cpu_percent']:.1f}%, RAM {stats['memory_mb']:.1f}MB, Children: {stats['children_count']}"
                )

            time.sleep(sample_interval)

    except KeyboardInterrupt:
        print("Interrupted by user")

    finally:
        # Clean up
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    # Calculate statistics
    if cpu_samples and memory_samples:
        results = {
            "avg_cpu": statistics.mean(cpu_samples),
            "max_cpu": max(cpu_samples),
            "avg_memory": statistics.mean(memory_samples),
            "max_memory": max(memory_samples),
            "samples": len(cpu_samples),
        }
    else:
        results = {"error": "No samples collected"}

    return results


def test_baseline():
    """Test baseline - sleep command without any wrapper"""
    print("\n" + "=" * 50)
    print("BASELINE TEST: sleep command (no wrapper)")
    print("=" * 50)

    return monitor_process_overhead(["sleep", "30"], duration=10)


def test_python_wrapper():
    """Test Python wrapper overhead"""
    print("\n" + "=" * 50)
    print("PYTHON WRAPPER TEST")
    print("=" * 50)

    return monitor_process_overhead(
        ["../toptle.py", "--interval", "2", "--", "sleep", "30"], duration=10
    )


def test_bash_wrapper():
    """Test Bash wrapper overhead"""
    print("\n" + "=" * 50)
    print("BASH WRAPPER TEST")
    print("=" * 50)

    return monitor_process_overhead(
        ["./process_monitor_wrapper.sh", "sleep", "30"], duration=10
    )


def test_python_wrapper_high_frequency():
    """Test Python wrapper with high update frequency"""
    print("\n" + "=" * 50)
    print("PYTHON WRAPPER TEST (High Frequency - 0.5s updates)")
    print("=" * 50)

    return monitor_process_overhead(
        ["../toptle.py", "--interval", "0.5", "--", "sleep", "30"], duration=10
    )


def compare_results(baseline, python_normal, bash, python_high_freq):
    """Compare the results and show overhead"""
    print("\n" + "=" * 60)
    print("PERFORMANCE COMPARISON RESULTS")
    print("=" * 60)

    tests = [
        ("Baseline (sleep only)", baseline),
        ("Bash Wrapper", bash),
        ("Python Wrapper (2s)", python_normal),
        ("Python Wrapper (0.5s)", python_high_freq),
    ]

    print(
        f"{'Test':<25} {'Avg CPU%':<10} {'Max CPU%':<10} {'Avg RAM MB':<12} {'Max RAM MB':<12}"
    )
    print("-" * 70)

    for name, result in tests:
        if "error" not in result:
            print(
                f"{name:<25} {result['avg_cpu']:<10.1f} {result['max_cpu']:<10.1f} "
                f"{result['avg_memory']:<12.1f} {result['max_memory']:<12.1f}"
            )
        else:
            print(f"{name:<25} ERROR: {result['error']}")

    # Calculate overhead
    if "error" not in baseline and "error" not in python_normal:
        print(f"\nPython Wrapper Overhead vs Baseline:")
        cpu_overhead = python_normal["avg_cpu"] - baseline["avg_cpu"]
        ram_overhead = python_normal["avg_memory"] - baseline["avg_memory"]
        print(f"  CPU: +{cpu_overhead:.1f}% (avg)")
        print(f"  RAM: +{ram_overhead:.1f}MB (avg)")

    if "error" not in python_normal and "error" not in python_high_freq:
        print(f"\nHigh Frequency Impact:")
        cpu_diff = python_high_freq["avg_cpu"] - python_normal["avg_cpu"]
        ram_diff = python_high_freq["avg_memory"] - python_normal["avg_memory"]
        print(f"  CPU: +{cpu_diff:.1f}% (0.5s vs 2s interval)")
        print(f"  RAM: +{ram_diff:.1f}MB (0.5s vs 2s interval)")


def main():
    print("Process Monitor Wrapper Performance Test")
    print("=" * 50)
    print("This test measures CPU and memory overhead of the wrappers")
    print("Each test runs for 10 seconds with 0.5s sampling")

    # Check dependencies
    if not os.path.exists("../toptle.py"):
        print("ERROR: toptle.py not found")
        sys.exit(1)

    if not os.path.exists("process_monitor_wrapper.sh"):
        print("ERROR: process_monitor_wrapper.sh not found")
        sys.exit(1)

    # Run tests
    baseline = test_baseline()
    python_normal = test_python_wrapper()
    bash = test_bash_wrapper()
    python_high_freq = test_python_wrapper_high_frequency()

    # Compare results
    compare_results(baseline, python_normal, bash, python_high_freq)

    # Recommendations
    print(f"\nRECOMMENDATIONS:")
    if "error" not in python_normal:
        if python_normal["avg_cpu"] < 5.0:
            print("✅ Python wrapper CPU usage is acceptable (<5%)")
        else:
            print("⚠️  Python wrapper CPU usage is high (>5%)")

        if python_normal["avg_memory"] < 50.0:
            print("✅ Python wrapper memory usage is acceptable (<50MB)")
        else:
            print("⚠️  Python wrapper memory usage is high (>50MB)")


if __name__ == "__main__":
    main()
