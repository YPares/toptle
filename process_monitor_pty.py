#!/usr/bin/env python3
"""
Advanced Process Monitor with PTY Integration
Intercepts terminal title changes and adds real-time resource usage information
"""

import os
import sys
import pty
import select
import subprocess
import threading
import time
import re
import signal
import argparse
from typing import Dict, List, Optional, Tuple

try:
    import psutil
except ImportError:
    print("ERROR: psutil module required. Install with: pip install psutil", file=sys.stderr)
    sys.exit(1)


class ProcessMonitor:
    def __init__(self, refresh_interval: float = 2.0, title_prefix: str = "📊"):
        self.refresh_interval = refresh_interval
        self.title_prefix = title_prefix
        self.main_process: Optional[psutil.Process] = None
        self.original_titles: List[str] = []
        self.last_stats = ""
        self.running = True
        
        # ANSI escape sequence patterns
        self.title_patterns = [
            re.compile(rb'\x1b\]0;([^\x07\x1b]*)\x07'),      # OSC 0 (both icon and window title)
            re.compile(rb'\x1b\]2;([^\x07\x1b]*)\x07'),      # OSC 2 (window title)
            re.compile(rb'\x1b\]1;([^\x07\x1b]*)\x07'),      # OSC 1 (icon title)
            re.compile(rb'\x1b\]0;([^\x07\x1b]*)\x1b\\'),    # Alternative terminator
            re.compile(rb'\x1b\]2;([^\x07\x1b]*)\x1b\\'),    # Alternative terminator
        ]
    
    def get_process_tree_stats(self, process: psutil.Process) -> Dict[str, float]:
        """Get CPU and memory statistics for process and all its children."""
        try:
            # Get all processes in the tree (including the main process)
            processes = [process] + process.children(recursive=True)
            
            total_cpu = 0.0
            total_memory = 0.0  # in MB
            
            for proc in processes:
                try:
                    # Get CPU percentage (averaged over interval)
                    cpu_percent = proc.cpu_percent()
                    # Get memory info in MB
                    memory_info = proc.memory_info()
                    memory_mb = memory_info.rss / (1024 * 1024)
                    
                    total_cpu += cpu_percent
                    total_memory += memory_mb
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            return {
                'cpu_percent': total_cpu,
                'memory_mb': total_memory,
                'process_count': len(processes)
            }
        
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {'cpu_percent': 0.0, 'memory_mb': 0.0, 'process_count': 0}
    
    def format_stats(self, stats: Dict[str, float]) -> str:
        """Format resource statistics into a readable string."""
        return f"{self.title_prefix} {stats['cpu_percent']:.1f}% CPU, {stats['memory_mb']:.1f}MB RAM"
    
    def modify_title_sequence(self, match: re.Match, stats_text: str) -> bytes:
        """Modify a terminal title escape sequence to include resource stats."""
        original_title = match.group(1).decode('utf-8', errors='replace')
        
        # Store original title for reference
        if original_title and original_title not in self.original_titles:
            self.original_titles.append(original_title)
        
        # Create new title with resource info
        if original_title:
            new_title = f"{original_title} | {stats_text}"
        else:
            new_title = stats_text
        
        # Reconstruct the escape sequence with the new title
        sequence_start = match.group(0)[:3]  # \x1b]0; or \x1b]2; etc.
        
        if match.group(0).endswith(b'\x07'):
            # Bell terminator
            return sequence_start + new_title.encode('utf-8', errors='replace') + b'\x07'
        else:
            # ST terminator (\x1b\\)
            return sequence_start + new_title.encode('utf-8', errors='replace') + b'\x1b\\'
    
    def process_output(self, data: bytes, stats_text: str) -> bytes:
        """Process output data, intercepting and modifying title sequences."""
        # Check for any title escape sequences
        for pattern in self.title_patterns:
            data = pattern.sub(lambda m: self.modify_title_sequence(m, stats_text), data)
        
        return data
    
    def stats_updater(self):
        """Background thread to update resource statistics."""
        while self.running and self.main_process:
            try:
                if self.main_process.is_running():
                    stats = self.get_process_tree_stats(self.main_process)
                    self.last_stats = self.format_stats(stats)
                else:
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            
            time.sleep(self.refresh_interval)
    
    def run_command(self, command: List[str]) -> int:
        """Run command in a PTY with resource monitoring and title interception."""
        
        print(f"🚀 Starting monitored process: {' '.join(command)}")
        print(f"📊 Resource monitoring interval: {self.refresh_interval}s")
        print(f"🔄 Intercepting terminal title changes...")
        print("")
        
        # Create PTY
        master_fd, slave_fd = pty.openpty()
        
        try:
            # Start the subprocess
            process = subprocess.Popen(
                command,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid
            )
            
            # Get psutil process handle
            self.main_process = psutil.Process(process.pid)
            
            # Start resource monitoring thread
            stats_thread = threading.Thread(target=self.stats_updater, daemon=True)
            stats_thread.start()
            
            # Close slave fd in parent process
            os.close(slave_fd)
            
            # Set up signal handlers
            def signal_handler(signum, frame):
                self.running = False
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
            
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            # Main I/O loop
            try:
                while self.running:
                    ready, _, _ = select.select([sys.stdin, master_fd], [], [], 0.1)
                    
                    if sys.stdin in ready:
                        # Forward input from terminal to process
                        try:
                            data = os.read(sys.stdin.fileno(), 1024)
                            if data:
                                os.write(master_fd, data)
                        except OSError:
                            break
                    
                    if master_fd in ready:
                        # Read output from process and modify it
                        try:
                            data = os.read(master_fd, 1024)
                            if data:
                                # Process and modify the output
                                modified_data = self.process_output(data, self.last_stats)
                                sys.stdout.buffer.write(modified_data)
                                sys.stdout.buffer.flush()
                            else:
                                break
                        except OSError:
                            break
                    
                    # Check if process is still running
                    if process.poll() is not None:
                        break
                
            except KeyboardInterrupt:
                pass
            
            # Clean up
            self.running = False
            
            # Wait for process to finish
            exit_code = process.wait()
            
            print(f"\n✅ Process completed with exit code: {exit_code}")
            
            return exit_code
            
        finally:
            # Clean up resources
            self.running = False
            try:
                os.close(master_fd)
            except OSError:
                pass
            
            # Reset terminal title
            sys.stdout.write('\033]0;Terminal\007')
            sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(
        description="Advanced process monitor with terminal title integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s htop
  %(prog)s --interval 1 --prefix "🔥" -- vim README.md
  %(prog)s -- bash -c "for i in {1..100}; do echo $i; sleep 0.1; done"
        """
    )
    
    parser.add_argument(
        '--interval',
        type=float,
        default=2.0,
        help='Resource monitoring update interval in seconds (default: 2.0)'
    )
    
    parser.add_argument(
        '--prefix',
        default='📊',
        help='Prefix for resource stats in title (default: 📊)'
    )
    
    parser.add_argument(
        'command',
        nargs=argparse.REMAINDER,
        help='Command to run with monitoring'
    )
    
    args = parser.parse_args()
    
    # Remove the '--' separator if present
    if args.command and args.command[0] == '--':
        args.command = args.command[1:]
    
    if not args.command:
        parser.error("No command specified")
    
    monitor = ProcessMonitor(
        refresh_interval=args.interval,
        title_prefix=args.prefix
    )
    
    try:
        exit_code = monitor.run_command(args.command)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()