#!/bin/bash
echo "=== Testing Process Tree Monitoring ==="
echo "Parent PID: $$"

# Spawn CPU-intensive child
(
    echo "Starting CPU-intensive child (PID: $$)"
    yes > /dev/null &
    child_pid=$!
    echo "CPU child PID: $child_pid"
    sleep 8
    kill $child_pid 2>/dev/null
    echo "CPU child finished"
) &

# Spawn memory-intensive child  
(
    echo "Starting memory-intensive child (PID: $$)"
    python3 -c "
import time
data = []
for i in range(10):
    data.append('x' * 10000000)  # 10MB chunks
    print(f'Allocated {(i+1)*10}MB')
    time.sleep(1)
print('Memory child finished')
" 2>/dev/null
) &

# Wait for children and show progress
for i in {1..10}; do
    echo "Parent iteration $i/10"
    sleep 1
done

wait
echo "=== All processes finished ==="