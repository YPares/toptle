#!/bin/bash

echo "=== Quick Performance Test for Process Monitor Wrappers ==="
echo

# Function to measure wrapper performance
test_wrapper() {
    local wrapper_cmd="$1"
    local test_name="$2"
    
    echo "Testing: $test_name"
    echo "Command: $wrapper_cmd"
    
    # Start the wrapper in background
    eval "$wrapper_cmd" &
    wrapper_pid=$!
    
    # Give it time to start
    sleep 2
    
    # Sample performance 5 times over 10 seconds
    echo "Sampling performance (5 samples over 10 seconds):"
    for i in {1..5}; do
        if kill -0 $wrapper_pid 2>/dev/null; then
            # Get stats for the wrapper process
            stats=$(ps -o pid,pcpu,pmem,rss,comm -p $wrapper_pid 2>/dev/null | tail -1)
            if [ -n "$stats" ]; then
                echo "  Sample $i: $stats"
            else
                echo "  Sample $i: Process not found"
            fi
        else
            echo "  Sample $i: Process finished"
            break
        fi
        sleep 2
    done
    
    # Clean up
    kill $wrapper_pid 2>/dev/null
    wait $wrapper_pid 2>/dev/null
    echo
}

# Test 1: Python wrapper (2s interval)
test_wrapper "../toptle.py --interval 2 -- sleep 15" "Python Wrapper (2s interval)"

# Test 2: Python wrapper (0.5s interval) 
test_wrapper "../toptle.py --interval 0.5 -- sleep 15" "Python Wrapper (0.5s interval)"

# Test 3: Bash wrapper
test_wrapper "./process_monitor_wrapper.sh sleep 15" "Bash Wrapper"

echo "=== Performance Test Complete ==="
echo
echo "Expected overhead guidelines:"
echo "✅ Good: CPU < 5%, RAM < 50MB"
echo "⚠️  Moderate: CPU 5-10%, RAM 50-100MB"  
echo "❌ High: CPU > 10%, RAM > 100MB"
