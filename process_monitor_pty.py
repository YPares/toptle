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
import struct
import fcntl
import termios
import tty
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
        self.master_fd: Optional[int] = None
        self.original_termios = None
        self.last_title_update = 0
        self.last_title_interception = 0  # Track when we last intercepted a title
        self.last_intercepted_title = ""  # Store the last intercepted title for reuse
        self.title_update_interval = 0.5  # Update title every 0.5 seconds if no title sequences
        
        # ANSI escape sequence patterns
        self.title_patterns = [
            re.compile(rb'\x1b\]0;([^\x07\x1b]*)\x07'),      # OSC 0 (both icon and window title)
            re.compile(rb'\x1b\]2;([^\x07\x1b]*)\x07'),      # OSC 2 (window title)
            re.compile(rb'\x1b\]1;([^\x07\x1b]*)\x07'),      # OSC 1 (icon title)
            re.compile(rb'\x1b\]0;([^\x07\x1b]*)\x1b\\'),    # Alternative terminator
            re.compile(rb'\x1b\]2;([^\x07\x1b]*)\x1b\\'),    # Alternative terminator
        ]
    
    def get_terminal_size(self) -> Tuple[int, int]:
        """Get current terminal size (rows, cols)."""
        try:
            # Try to get size from stdin
            size_data = struct.pack('HHHH', 0, 0, 0, 0)
            result = fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, size_data)
            rows, cols, _, _ = struct.unpack('HHHH', result)
            return (rows, cols) if rows and cols else (24, 80)
        except (OSError, IOError):
            # Fallback to environment variables or default
            try:
                rows = int(os.environ.get('LINES', 24))
                cols = int(os.environ.get('COLUMNS', 80))
                return (rows, cols)
            except ValueError:
                return (24, 80)
    
    def set_pty_size(self, fd: int, rows: int, cols: int) -> None:
        """Set the size of a PTY."""
        try:
            size_data = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, size_data)
        except (OSError, IOError):
            pass  # Ignore errors - size setting is best effort
    
    def handle_window_size_change(self, signum, frame):
        """Handle SIGWINCH signal and forward to PTY."""
        if self.master_fd is not None:
            rows, cols = self.get_terminal_size()
            self.set_pty_size(self.master_fd, rows, cols)
    
    def setup_raw_terminal(self):
        """Set up terminal in raw mode for transparent pass-through."""
        try:
            self.original_termios = termios.tcgetattr(sys.stdin.fileno())
            tty.setraw(sys.stdin.fileno())
        except (OSError, IOError, termios.error):
            pass  # Not a terminal or can't set raw mode
    
    def restore_terminal(self):
        """Restore original terminal settings."""
        if self.original_termios is not None:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.original_termios)
            except (OSError, IOError, termios.error):
                pass
    
    def send_proactive_title_update(self):
        """Send a proactive title update for processes that don't set titles."""
        if self.last_stats:
            current_time = time.time()
            
            # Don't send proactive updates if we recently intercepted a title
            # This prevents overwriting intercepted titles with proactive ones
            time_since_interception = current_time - self.last_title_interception
            if time_since_interception < 1.0:  # Suppress for 1 second after interception
                return
            
            if current_time - self.last_title_update >= self.title_update_interval:
                # Create title that preserves last intercepted title if available
                if self.last_intercepted_title:
                    title_content = f"{self.last_intercepted_title} | {self.last_stats}"
                else:
                    title_content = self.last_stats
                
                # Send title directly to terminal
                title_sequence = f'\033]0;{title_content}\007'
                try:
                    sys.stdout.write(title_sequence)
                    sys.stdout.flush()
                    self.last_title_update = current_time
                except (OSError, IOError):
                    pass  # Ignore output errors
    
    def is_likely_interactive(self, command: List[str]) -> bool:
        """Detect if a command is likely to be an interactive application"""
        if not command:
            return False
        
        # Get the base command name
        cmd_name = os.path.basename(command[0])
        
        # Known interactive applications that need raw terminal mode
        interactive_apps = {
            'vim', 'vi', 'nano', 'emacs',
            'htop', 'top', 'btop', 'atop',
            'less', 'more', 'man',
            'tmux', 'screen',
            'bash', 'sh', 'zsh', 'fish',
            'python', 'python3', 'ipython',
            'node', 'irb', 'ghci'
        }
        
        # Also check for common non-interactive commands to optimize
        non_interactive_apps = {
            'sleep', 'echo', 'cat', 'grep', 'find', 'sort',
            'make', 'gcc', 'clang', 'cargo', 'npm', 'pip',
            'git', 'curl', 'wget', 'tar', 'gzip'
        }
        
        if cmd_name in non_interactive_apps:
            return False
        
        if cmd_name in interactive_apps:
            return True
        
        # Default to interactive for unknown commands to be safe
        return True
    
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
        
        # Store the intercepted title for reuse in proactive updates
        self.last_intercepted_title = original_title
        
        # Record that we intercepted a title (to suppress proactive updates briefly)
        self.last_title_interception = time.time()
        
        # Create new title with resource info
        if original_title:
            new_title = f"{original_title} | {stats_text}"
        else:
            new_title = stats_text
        
        # Reconstruct the escape sequence with the new title  
        sequence_start = match.group(0)[:4]  # \x1b]0; or \x1b]2; etc. (include semicolon)
        
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
                    
                    # Send proactive title update for applications that don't set titles
                    self.send_proactive_title_update()
                else:
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            
            time.sleep(self.refresh_interval)
    
    def run_command(self, command: List[str]) -> int:
        """Run command with resource monitoring and title interception."""
        
        print(f"🚀 Starting monitored process: {' '.join(command)}")
        print(f"📊 Resource monitoring interval: {self.refresh_interval}s")
        
        # Detect if command needs full PTY support
        is_interactive = self.is_likely_interactive(command)
        
        if is_interactive:
            print(f"🔄 Interactive mode: Full PTY with title interception...")
            return self._run_with_pty(command)
        else:
            print(f"🔄 Non-interactive mode: Direct piping with proactive titles...")
            return self._run_direct(command)
    
    def _run_direct(self, command: List[str]) -> int:
        """Run command using direct subprocess for non-interactive commands."""
        print("")
        
        try:
            # Start subprocess with direct piping
            process = subprocess.Popen(
                command,
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            
            # Get psutil process handle
            self.main_process = psutil.Process(process.pid)
            
            # Start resource monitoring thread
            stats_thread = threading.Thread(target=self.stats_updater, daemon=True)
            stats_thread.start()
            
            # Wait for process to finish
            exit_code = process.wait()
            
            print(f"\n✅ Process completed with exit code: {exit_code}")
            return exit_code
            
        finally:
            # Clean up resources
            self.running = False
            
            # Reset terminal title
            try:
                sys.stdout.write('\033]0;Terminal\007')
                sys.stdout.flush()
            except (OSError, IOError):
                pass  # Ignore errors during cleanup
        
    def _run_with_pty(self, command: List[str]) -> int:
        """Run command using PTY for full interactive support."""
        
        # Create PTY
        master_fd, slave_fd = pty.openpty()
        self.master_fd = master_fd
        
        # Set initial PTY size to match current terminal
        rows, cols = self.get_terminal_size()
        self.set_pty_size(master_fd, rows, cols)
        
        # Set up raw terminal mode for interactive applications
        self.setup_raw_terminal()
        
        # Set up SIGWINCH handler for window size changes
        signal.signal(signal.SIGWINCH, self.handle_window_size_change)
        
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
            
            # Get initial stats before starting I/O loop
            initial_stats = self.get_process_tree_stats(self.main_process)
            self.last_stats = self.format_stats(initial_stats)
            
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
            
            # Main I/O loop - optimized for efficiency
            try:
                # Use longer timeout to reduce CPU usage - wake up only when needed
                timeout = 0.5  # Half second timeout - responsive but efficient
                
                while self.running:
                    ready, _, _ = select.select([sys.stdin, master_fd], [], [], timeout)
                    
                    # Process input if available
                    if sys.stdin in ready:
                        try:
                            # Use larger buffer for efficiency
                            data = os.read(sys.stdin.fileno(), 4096)
                            if data:
                                os.write(master_fd, data)
                        except OSError:
                            break
                    
                    # Process output if available  
                    if master_fd in ready:
                        try:
                            # Use larger buffer for efficiency
                            data = os.read(master_fd, 4096)
                            if data:
                                # Process and modify the output
                                modified_data = self.process_output(data, self.last_stats)
                                sys.stdout.buffer.write(modified_data)
                                sys.stdout.buffer.flush()
                            else:
                                break
                        except OSError:
                            break
                    
                    # Only check process status if no I/O occurred (avoid syscall overhead)
                    if not ready and process.poll() is not None:
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
            
            # Restore terminal settings
            self.restore_terminal()
            
            # Reset SIGWINCH handler to default
            signal.signal(signal.SIGWINCH, signal.SIG_DFL)
            
            try:
                os.close(master_fd)
            except OSError:
                pass
            
            # Reset terminal title
            try:
                sys.stdout.write('\033]0;Terminal\007')
                sys.stdout.flush()
            except (OSError, IOError):
                pass  # Ignore errors during cleanup
            
            self.master_fd = None


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