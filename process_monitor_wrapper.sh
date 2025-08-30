#!/bin/bash

# Process Monitor Wrapper - Intercepts terminal titles and adds resource usage info
# Usage: ./process_monitor_wrapper.sh [command] [args...]

# Configuration
REFRESH_INTERVAL=2
TITLE_PREFIX="📊"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to get CPU and memory usage for a process tree
get_process_stats() {
    local main_pid=$1
    local total_cpu=0
    local total_mem=0
    local total_mem_mb=0
    
    # Get all child PIDs (including the main process)
    local pids=$(pstree -p "$main_pid" 2>/dev/null | grep -o '([0-9]*)' | tr -d '()' | sort -u)
    
    if [ -z "$pids" ]; then
        # Fallback: just use the main PID if pstree fails
        pids="$main_pid"
    fi
    
    for pid in $pids; do
        if [ -d "/proc/$pid" ]; then
            # Read CPU usage (this is cumulative, we'll calculate percentage differently)
            local cpu_data=$(ps -o pcpu= -p "$pid" 2>/dev/null | tr -d ' ')
            local mem_data=$(ps -o pmem= -p "$pid" 2>/dev/null | tr -d ' ')
            local mem_kb=$(ps -o rss= -p "$pid" 2>/dev/null | tr -d ' ')
            
            if [ -n "$cpu_data" ] && [ -n "$mem_data" ] && [ -n "$mem_kb" ]; then
                total_cpu=$(echo "$total_cpu + $cpu_data" | bc -l 2>/dev/null || echo "$total_cpu")
                total_mem=$(echo "$total_mem + $mem_data" | bc -l 2>/dev/null || echo "$total_mem")
                total_mem_mb=$(echo "$total_mem_mb + $mem_kb" | bc -l 2>/dev/null || echo "$total_mem_mb")
            fi
        fi
    done
    
    # Convert memory from KB to MB
    total_mem_mb=$(echo "scale=1; $total_mem_mb / 1024" | bc -l 2>/dev/null || echo "0")
    
    # Format the output
    printf "%.1f%% CPU, %.1fMB RAM" "$total_cpu" "$total_mem_mb"
}

# Function to set terminal title
set_title() {
    printf '\033]0;%s\007' "$1"
}

# Function to parse and modify terminal title from process output
process_title_updates() {
    local main_pid=$1
    local original_title=""
    local last_title=""
    
    while kill -0 "$main_pid" 2>/dev/null; do
        # Get current resource usage
        local stats=$(get_process_stats "$main_pid")
        
        # Try to detect if a title was set by reading recent terminal escape sequences
        # This is a simplified approach - in practice, we'd need to intercept the actual output
        
        # Get current window title (this may not work in all terminals)
        local current_title
        
        # For now, we'll just update with resource info periodically
        if [ -n "$original_title" ]; then
            local new_title="$original_title | $TITLE_PREFIX $stats"
        else
            local new_title="$TITLE_PREFIX $stats"
        fi
        
        if [ "$new_title" != "$last_title" ]; then
            set_title "$new_title"
            last_title="$new_title"
        fi
        
        sleep "$REFRESH_INTERVAL"
    done
}

# Function to run process and monitor it
run_with_monitoring() {
    local cmd="$@"
    
    if [ $# -eq 0 ]; then
        echo -e "${RED}Error: No command provided${NC}"
        echo "Usage: $0 [command] [args...]"
        exit 1
    fi
    
    echo -e "${GREEN}Starting monitored process: ${YELLOW}$cmd${NC}"
    echo -e "${GREEN}Resource monitoring interval: ${YELLOW}${REFRESH_INTERVAL}s${NC}"
    echo ""
    
    # Store original title
    local original_title="Monitoring: $cmd"
    set_title "$original_title"
    
    # Start the process in background
    "$@" &
    local main_pid=$!
    
    # Start title monitoring in background
    (
        sleep 1  # Give process time to start
        process_title_updates "$main_pid"
    ) &
    local monitor_pid=$!
    
    # Handle cleanup on script termination
    trap "kill $monitor_pid 2>/dev/null; kill $main_pid 2>/dev/null; set_title 'Terminal'; exit" INT TERM
    
    # Wait for the main process to finish
    wait "$main_pid"
    local exit_code=$?
    
    # Clean up
    kill "$monitor_pid" 2>/dev/null
    set_title "Terminal"
    
    echo ""
    echo -e "${GREEN}Process completed with exit code: ${YELLOW}$exit_code${NC}"
    
    return $exit_code
}

# Check dependencies
check_dependencies() {
    local missing_deps=()
    
    command -v pstree >/dev/null 2>&1 || missing_deps+=("pstree")
    command -v bc >/dev/null 2>&1 || missing_deps+=("bc")
    command -v ps >/dev/null 2>&1 || missing_deps+=("ps")
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        echo -e "${RED}Missing dependencies: ${missing_deps[*]}${NC}"
        echo "Please install them using your package manager."
        echo "Example: sudo apt-get install psmisc bc procps"
        exit 1
    fi
}

# Main execution
main() {
    check_dependencies
    run_with_monitoring "$@"
}

# Run if script is executed directly
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi