#!/usr/bin/env python3
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
from typing import List, Optional, Tuple
from dataclasses import dataclass

try:
    import psutil
except ImportError:
    print(
        "ERROR: psutil module required. Install with: pip install psutil",
        file=sys.stderr,
    )
    sys.exit(1)


# Pre-compiled regex patterns for title sequence detection (module-level for efficiency)
TITLE_SEQUENCE_PATTERNS = [
    re.compile(rb"\x1b\]0;([^\x07\x1b]*)\x07"),  # OSC 0 (window and icon title)
    re.compile(rb"\x1b\]2;([^\x07\x1b]*)\x07"),  # OSC 2 (window title)
    re.compile(rb"\x1b\]1;([^\x07\x1b]*)\x07"),  # OSC 1 (icon title)
    re.compile(rb"\x1b\]0;([^\x07\x1b]*)\x1b\\"),  # Alternative terminator
    re.compile(rb"\x1b\]2;([^\x07\x1b]*)\x1b\\"),  # Alternative terminator
]


# Constants
class Config:
    """Configuration constants for the process monitor."""

    # Timing constants
    DEFAULT_REFRESH_INTERVAL = 2.0
    TITLE_UPDATE_INTERVAL = 0.5
    TITLE_SUPPRESSION_DURATION = 1.0  # Suppress proactive updates after interception
    PTY_TIMEOUT = 0.5

    # Buffer sizes
    IO_BUFFER_SIZE = 4096

    # Memory conversion
    BYTES_TO_MB = 1024 * 1024

    # Terminal sequences
    TERMINAL_RESET_SEQUENCE = "\033]0;Terminal\007"
    TITLE_SEQUENCE_FORMAT = "\033]0;{}\007"

    # Default values
    DEFAULT_TITLE_PREFIX = "🐢"
    DEFAULT_TITLE_SUFFIX = "🐢"



@dataclass
class ProcessStats:
    """Resource statistics for a process tree."""

    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    disk_read_rate: float = 0.0
    disk_write_rate: float = 0.0
    net_sent_rate: float = 0.0
    net_recv_rate: float = 0.0
    open_files: int = 0
    thread_count: int = 0
    process_count: int = 0


class Toptle:
    def __init__(
        self,
        refresh_interval: float = Config.DEFAULT_REFRESH_INTERVAL,
        title_prefix: str = Config.DEFAULT_TITLE_PREFIX,
        title_suffix: str = Config.DEFAULT_TITLE_SUFFIX,
        metrics: str = "cpu,ram",
        verbose: bool = False,
        pty_mode: bool = False
    ):
        self.refresh_interval = refresh_interval
        self.title_prefix = title_prefix
        self.title_suffix = title_suffix

        # Parse and validate metrics
        self.metrics = self._parse_metrics(metrics)

        self.verbose = verbose
        self.pty_mode = pty_mode

        self.main_process: Optional[psutil.Process] = None
        self.original_titles: List[str] = []
        self.last_stats = ""
        self.running = True
        self.master_fd: Optional[int] = None
        self.original_termios = None
        self.last_title_update = 0
        self.last_title_interception = 0
        self.last_intercepted_title = ""
        self.default_title = ""

        # For rate calculations
        self.last_io_counters = None
        self.last_net_counters = None
        self.last_measurement_time = 0

    def _parse_metrics(self, metrics_str: str) -> List[str]:
        """Parse and validate metrics string."""
        available_metrics_set = {"cpu", "ram", "disk", "net", "files", "threads"}
        available_metrics_list = ["cpu", "ram", "disk", "net", "files", "threads"]

        if metrics_str.lower() == "all":
            return available_metrics_list.copy()

        metrics = [m.strip().lower() for m in metrics_str.split(",")]

        # Validate all metrics are available using set operations (faster)
        # but preserve the original order by only using sets for validation
        invalid_metrics = set(metrics) - available_metrics_set
        if invalid_metrics:
            raise ValueError(
                f"Invalid metrics: {', '.join(sorted(invalid_metrics))}. "
                f"Available: {', '.join(available_metrics_list)}"
            )

        return metrics

    def get_terminal_size(self) -> Tuple[int, int]:
        """Get current terminal size (rows, cols)."""
        try:
            # Try to get size from stdin
            size_data = struct.pack("HHHH", 0, 0, 0, 0)
            result = fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, size_data)
            rows, cols, _, _ = struct.unpack("HHHH", result)
            return (rows, cols) if rows and cols else (24, 80)
        except (OSError, IOError):
            # Fallback to environment variables or default
            try:
                rows = int(os.environ.get("LINES", 24))
                cols = int(os.environ.get("COLUMNS", 80))
                return (rows, cols)
            except ValueError:
                return (24, 80)

    def set_pty_size(self, fd: int, rows: int, cols: int) -> None:
        """Set the size of a PTY."""
        try:
            size_data = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, size_data)
        except (OSError, IOError):
            pass  # Ignore errors - size setting is best effort

    def handle_window_size_change(self, signum, frame):
        """Handle SIGWINCH signal and forward to PTY."""
        if self.master_fd is not None:
            rows, cols = self.get_terminal_size()
            self.set_pty_size(self.master_fd, rows, cols)
            
            # Forward SIGWINCH to the child process group
            if hasattr(self, 'main_process') and self.main_process is not None:
                try:
                    os.killpg(self.main_process.pid, signal.SIGWINCH)
                except (ProcessLookupError, OSError):
                    pass  # Process may have already terminated

    def setup_raw_terminal(self):
        """Set up terminal for transparent pass-through while preserving signals."""
        try:
            self.original_termios = termios.tcgetattr(sys.stdin.fileno())
            # Configure proper raw mode while preserving signal handling
            raw_attrs = termios.tcgetattr(sys.stdin.fileno())
            
            # Input flags (c_iflag): disable input processing but preserve basics
            raw_attrs[0] &= ~(termios.BRKINT | termios.ICRNL | termios.INPCK | 
                             termios.ISTRIP | termios.IXON)
            
            # Output flags (c_oflag): disable output processing
            raw_attrs[1] &= ~termios.OPOST
            
            # Control flags (c_cflag): ensure 8-bit chars
            raw_attrs[2] |= termios.CS8
            
            # Local flags (c_lflag): disable canonical mode and echo, but KEEP ISIG for signals
            raw_attrs[3] &= ~(termios.ECHO | termios.ICANON | termios.IEXTEN)
            # Note: ISIG is intentionally preserved for signal handling
            
            # Set read timeouts for non-blocking reads
            raw_attrs[6][termios.VMIN] = 0
            raw_attrs[6][termios.VTIME] = 1
            
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, raw_attrs)
        except (OSError, IOError, termios.error):
            pass  # Not a terminal or can't set raw mode

    def restore_terminal(self):
        """Restore original terminal settings."""
        if self.original_termios is not None:
            try:
                termios.tcsetattr(
                    sys.stdin.fileno(), termios.TCSADRAIN, self.original_termios
                )
            except (OSError, IOError, termios.error):
                pass

    def send_proactive_title_update(self):
        """Send a proactive title update for processes that don't set titles."""
        if self.last_stats:
            current_time = time.time()

            # Don't send proactive updates if we recently intercepted a title
            # This prevents overwriting intercepted titles with proactive ones
            time_since_interception = current_time - self.last_title_interception
            if time_since_interception < Config.TITLE_SUPPRESSION_DURATION:
                return

            if current_time - self.last_title_update >= Config.TITLE_UPDATE_INTERVAL:
                # Create title that preserves last intercepted title if available
                if self.last_intercepted_title:
                    title_content = f"{self.last_intercepted_title} {self.last_stats}"
                elif self.default_title:
                    title_content = f"{self.default_title} {self.last_stats}"
                else:
                    title_content = self.last_stats

                # Send title directly to terminal
                title_sequence = Config.TITLE_SEQUENCE_FORMAT.format(title_content)
                try:
                    sys.stdout.write(title_sequence)
                    sys.stdout.flush()
                    self.last_title_update = current_time
                except (OSError, IOError):
                    pass  # Ignore output errors


    def get_process_tree_stats(self, process: psutil.Process) -> ProcessStats:
        """Get resource statistics for process and all its children."""
        try:
            # Get all processes in the tree (including the main process)
            processes = [process] + process.children(recursive=True)

            # Basic counters
            total_cpu = 0.0
            total_memory = 0.0  # in MB
            total_files = 0
            total_threads = 0

            # I/O counters (for rate calculation)
            total_disk_read = 0
            total_disk_write = 0

            current_time = time.time()

            for proc in processes:
                try:
                    # CPU and memory (existing)
                    # Use interval parameter to get immediate CPU measurement
                    cpu_percent = proc.cpu_percent(interval=0.1)
                    memory_info = proc.memory_info()
                    memory_mb = memory_info.rss / Config.BYTES_TO_MB

                    total_cpu += cpu_percent
                    total_memory += memory_mb

                    # File descriptors and threads (if requested)
                    if "files" in self.metrics:
                        total_files += (
                            proc.num_fds()
                            if hasattr(proc, "num_fds")
                            else len(proc.open_files())
                        )

                    if "threads" in self.metrics:
                        total_threads += proc.num_threads()

                    # Disk I/O (if requested)
                    if "disk" in self.metrics:
                        try:
                            io_counters = proc.io_counters()
                            total_disk_read += io_counters.read_bytes
                            total_disk_write += io_counters.write_bytes
                        except (AttributeError, psutil.AccessDenied):
                            pass

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Network I/O (system-wide, if requested)
            net_sent_rate = 0.0
            net_recv_rate = 0.0
            if "net" in self.metrics:
                try:
                    net_counters = psutil.net_io_counters()
                    if (
                        net_counters
                        and self.last_net_counters
                        and self.last_measurement_time
                    ):
                        time_delta = current_time - self.last_measurement_time
                        if time_delta > 0:
                            net_sent_rate = (
                                net_counters.bytes_sent
                                - self.last_net_counters.bytes_sent
                            ) / time_delta
                            net_recv_rate = (
                                net_counters.bytes_recv
                                - self.last_net_counters.bytes_recv
                            ) / time_delta

                    self.last_net_counters = net_counters
                except (AttributeError, psutil.AccessDenied):
                    pass

            # Disk I/O rates
            disk_read_rate = 0.0
            disk_write_rate = 0.0
            if (
                "disk" in self.metrics
                and self.last_io_counters
                and self.last_measurement_time
            ):
                time_delta = current_time - self.last_measurement_time
                if time_delta > 0:
                    disk_read_rate = (
                        total_disk_read - self.last_io_counters["read"]
                    ) / time_delta
                    disk_write_rate = (
                        total_disk_write - self.last_io_counters["write"]
                    ) / time_delta

            # Store current I/O counters for next calculation
            if "disk" in self.metrics:
                self.last_io_counters = {
                    "read": total_disk_read,
                    "write": total_disk_write,
                }

            self.last_measurement_time = current_time

            return ProcessStats(
                cpu_percent=total_cpu,
                memory_mb=total_memory,
                disk_read_rate=disk_read_rate,
                disk_write_rate=disk_write_rate,
                net_sent_rate=net_sent_rate,
                net_recv_rate=net_recv_rate,
                open_files=total_files,
                thread_count=total_threads,
                process_count=len(processes),
            )

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return ProcessStats()

    def _cleanup_resources(
        self, master_fd: Optional[int] = None, reset_signals: bool = False
    ):
        """Common cleanup logic for resources and terminal state."""
        self.running = False

        if reset_signals:
            # Reset SIGWINCH handler to default
            signal.signal(signal.SIGWINCH, signal.SIG_DFL)

        # Restore terminal settings
        self.restore_terminal()

        # Close PTY master fd if provided
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass

        # Reset terminal title
        try:
            sys.stdout.write(Config.TERMINAL_RESET_SEQUENCE)
            sys.stdout.flush()
        except (OSError, IOError):
            pass  # Ignore errors during cleanup

        self.master_fd = None

    def _setup_signal_handlers(self, process: subprocess.Popen, is_pty_process: bool = False):
        """Set up signal handlers for proper signal forwarding."""

        def signal_handler(signum, frame):
            
            try:
                if is_pty_process:
                    # For PTY processes, use control character forwarding
                    if signum == signal.SIGINT:
                        # For PTY processes, send control character to let PTY generate signal
                        # This matches how real terminals work: Ctrl+C -> control char -> PTY generates SIGINT
                        # Interactive apps expect signals from terminal line discipline, not programmatic
                        if hasattr(self, 'master_fd') and self.master_fd is not None:
                            try:
                                os.write(self.master_fd, b'\x03')  # Send Ctrl+C control character
                            except (OSError, IOError):
                                pass
                        else:
                            # Fallback to signal if no PTY available
                            try:
                                os.killpg(process.pid, signum)
                            except (ProcessLookupError, OSError):
                                pass
                    else:
                        # For other signals (SIGTERM), terminate toptle and forward signal
                        self.running = False
                        try:
                            os.killpg(process.pid, signum)
                        except (ProcessLookupError, OSError):
                            pass
                else:
                    # For non-PTY processes, send signal directly
                    if signum == signal.SIGINT:
                        process.send_signal(signal.SIGINT)
                    else:
                        self.running = False
                        process.terminate()
            except (ProcessLookupError, OSError):
                pass

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def format_stats(self, stats: ProcessStats) -> str:
        """Format resource statistics into a readable string based on selected metrics."""
        metric_parts = []

        for metric in self.metrics:
            if metric == "cpu":
                metric_parts.append(f"{stats.cpu_percent:.1f}% CPU")
            elif metric == "ram":
                metric_parts.append(f"{stats.memory_mb:.1f}MB RAM")
            elif metric == "disk":
                formatted_rates = self._format_io_rates(
                    stats.disk_read_rate, stats.disk_write_rate
                )
                metric_parts.append(f"disk {formatted_rates}")
            elif metric == "net":
                formatted_rates = self._format_io_rates(
                    stats.net_sent_rate, stats.net_recv_rate
                )
                metric_parts.append(f"net {formatted_rates}")
            elif metric == "files":
                metric_parts.append(f"{stats.open_files} files")
            elif metric == "threads":
                metric_parts.append(f"{stats.thread_count} threads")

        if metric_parts:
            return f"{self.title_prefix}{', '.join(metric_parts)}{self.title_suffix}"
        else:
            return f"{self.title_prefix}NO METRICS!{self.title_suffix}"

    def _format_rate_with_unit(self, bytes_per_sec: float) -> str:
        """Format a rate value with appropriate unit."""
        if bytes_per_sec >= 1024 * 1024:  # MB/s
            return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"
        elif bytes_per_sec >= 1024:  # KB/s
            return f"{bytes_per_sec / 1024:.0f} KB/s"
        else:  # B/s
            return f"{bytes_per_sec:.0f} B/s"

    def _format_io_rates(self, read_rate: float, write_rate: float) -> str:
        """Format read/write rates with shared unit."""
        max_rate = max(read_rate, write_rate)

        if max_rate >= 1024 * 1024:  # MB/s
            read_val = f"{read_rate / (1024 * 1024):.1f}"
            write_val = f"{write_rate / (1024 * 1024):.1f}"
            return f"↑{read_val} ↓{write_val} MB/s"
        elif max_rate >= 1024:  # KB/s
            read_val = f"{read_rate / 1024:.0f}"
            write_val = f"{write_rate / 1024:.0f}"
            return f"↑{read_val} ↓{write_val} KB/s"
        else:  # B/s
            return f"↑{read_rate:.0f} ↓{write_rate:.0f} B/s"

    def modify_title_sequence(self, match: re.Match, stats_text: str) -> bytes:
        """Modify a terminal title escape sequence to include resource stats."""
        original_title = match.group(1).decode("utf-8", errors="replace")

        # Store original title for reference
        if original_title and original_title not in self.original_titles:
            self.original_titles.append(original_title)

        # Store the intercepted title for reuse in proactive updates
        self.last_intercepted_title = original_title

        # Record that we intercepted a title (to suppress proactive updates briefly)
        self.last_title_interception = time.time()

        # Create new title with resource info
        if original_title:
            new_title = f"{original_title} {stats_text}"
        else:
            new_title = stats_text

        # Reconstruct the escape sequence with the new title
        sequence_start = match.group(0)[
            :4
        ]  # \x1b]0; or \x1b]2; etc. (include semicolon)

        if match.group(0).endswith(b"\x07"):
            # Bell terminator
            return (
                sequence_start + new_title.encode("utf-8", errors="replace") + b"\x07"
            )
        else:
            # ST terminator (\x1b\\)
            return (
                sequence_start + new_title.encode("utf-8", errors="replace") + b"\x1b\\"
            )

    def process_output(self, data: bytes, stats_text: str) -> bytes:
        """Process output data, intercepting and modifying title sequences."""
        # Check for any title escape sequences
        for pattern in TITLE_SEQUENCE_PATTERNS:
            data = pattern.sub(
                lambda m: self.modify_title_sequence(m, stats_text), data
            )

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

        # Set up default title using PWD and command
        try:
            pwd = os.path.basename(os.getcwd())
            command_name = os.path.basename(command[0]) if command else "unknown"
            self.default_title = f"{pwd}> {command_name}"
        except (OSError, IndexError):
            self.default_title = f"toptle> {' '.join(command[:2])}"

        if self.verbose:
            print(f"🐢 Refreshing {','.join(self.metrics)} every {self.refresh_interval}s")
        
        if self.pty_mode:
            if self.verbose:
                print("🐢 PTY mode (full terminal emulation)")
            return self._run_with_pty(command)
        else:
            if self.verbose:
                print("🐢 Direct mode (transparent piping)")
            return self._run_direct(command)

    def _run_direct(self, command: List[str]) -> int:
        """Run command using direct subprocess with transparent piping."""
        try:
            # Start subprocess with direct piping
            process = subprocess.Popen(
                command, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr
            )

            # Get psutil process handle
            self.main_process = psutil.Process(process.pid)

            # Set up signal handlers for clean termination (direct mode)
            self._setup_signal_handlers(process, is_pty_process=False)

            # Start resource monitoring thread
            stats_thread = threading.Thread(target=self.stats_updater, daemon=True)
            stats_thread.start()

            # Wait for process to finish
            exit_code = process.wait()

            if self.verbose:
                print(f"\n🐢 Process completed with exit code: {exit_code}")

            return exit_code

        finally:
            # Clean up resources
            self._cleanup_resources()

    def _run_with_pty(self, command: List[str]) -> int:
        """Run command using PTY for full terminal emulation."""

        # Create PTY
        master_fd, slave_fd = pty.openpty()
        self.master_fd = master_fd

        # Set initial PTY size to match current terminal
        rows, cols = self.get_terminal_size()
        self.set_pty_size(master_fd, rows, cols)

        # Set up terminal mode for PTY applications
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
                preexec_fn=os.setsid,
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

            # Set up signal handlers for PTY processes with special forwarding
            self._setup_signal_handlers(process, is_pty_process=True)

            # Main I/O loop - optimized for efficiency
            try:
                while self.running:
                    ready, _, _ = select.select(
                        [sys.stdin, master_fd], [], [], Config.PTY_TIMEOUT
                    )

                    # Process input if available
                    if sys.stdin in ready:
                        try:
                            data = os.read(sys.stdin.fileno(), Config.IO_BUFFER_SIZE)
                            if data:
                                os.write(master_fd, data)
                        except OSError:
                            break

                    # Process output if available
                    if master_fd in ready:
                        try:
                            data = os.read(master_fd, Config.IO_BUFFER_SIZE)
                            if data:
                                # Process and modify the output
                                modified_data = self.process_output(
                                    data, self.last_stats
                                )
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

            if self.verbose:
                print(f"\n🐢 Process completed with exit code: {exit_code}")

            return exit_code

        finally:
            # Clean up resources
            self._cleanup_resources(master_fd, reset_signals=True)


def main():
    parser = argparse.ArgumentParser(
        description="Toptle - Resource stats in your terminal title",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -- python -m http.server 8000          # Direct mode (default, transparent)
  %(prog)s --pty -- helix file.txt               # PTY mode (full terminal emulation)  
  %(prog)s --pty -- vim README.md                # PTY mode for edge cases
  %(prog)s -r 0.5 -p "🔥" -- make build           # Fast updates with custom prefix
  %(prog)s -m cpu,ram,disk -- ./build-script.sh   # Monitor disk I/O
  %(prog)s -- bash -c "for i in {1..100}; do echo $i; sleep 0.1; done"
        """,
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose mode",
    )

    parser.add_argument(
        "--refresh",
        "-r",
        type=float,
        default=Config.DEFAULT_REFRESH_INTERVAL,
        help="Resource monitoring refresh interval in seconds (default: 2.0)",
    )

    parser.add_argument(
        "--prefix",
        "-p",
        default=Config.DEFAULT_TITLE_PREFIX,
        help="Prefix for resource stats in title",
    )

    parser.add_argument(
        "--suffix",
        "-s",
        default=Config.DEFAULT_TITLE_PREFIX,
        help="Suffix for resource stats in title",
    )

    parser.add_argument(
        "--metrics",
        "-m",
        default="cpu,ram",
        help="Metrics to display: cpu,ram,disk,net,files,threads,all (default: cpu,ram)",
    )

    parser.add_argument(
        "--pty",
        "-t", 
        action="store_true",
        help="Use PTY mode: full terminal emulation (rarely needed)",
    )

    parser.add_argument(
        "command", nargs=argparse.REMAINDER, help="Command to run with monitoring"
    )

    args = parser.parse_args()

    # Remove the '--' separator if present
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]

    if not args.command:
        parser.error("No command specified")

    monitor = Toptle(
        refresh_interval=args.refresh,
        title_prefix=args.prefix,
        title_suffix=args.suffix,
        metrics=args.metrics,
        verbose=args.verbose,
        pty_mode=args.pty
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
