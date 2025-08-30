#!/bin/bash

# Test script that changes terminal title multiple times
echo "=== Testing Terminal Title Changes ==="

# Function to set terminal title
set_title() {
    printf '\033]0;%s\007' "$1"
    echo "Set title to: '$1'"
}

# Initial title
set_title "Starting Test Process"
sleep 2

# Change title multiple times during execution
for i in {1..5}; do
    set_title "Processing Step $i of 5"
    echo "Executing step $i..."
    
    # Do some work that uses resources
    if [ $i -eq 3 ]; then
        echo "Step 3: Starting CPU-intensive task"
        (yes > /dev/null) &
        cpu_pid=$!
        sleep 3
        kill $cpu_pid 2>/dev/null
        echo "CPU task finished"
    else
        sleep 2
    fi
done

# Final title change
set_title "Test Completed Successfully"
echo "All steps completed"
sleep 2

# Another title with special characters
set_title "Final Status: ✅ All Good! 🎉"
echo "Test finished with special title"
sleep 1

echo "=== Test script completed ==="