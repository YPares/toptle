# Toptle

A transparent process monitor that displays real-time CPU and memory usage in your terminal title bar. Works seamlessly with both interactive applications (vim, htop, less) and non-interactive commands (make, git) without interfering with their operation.

## How it works

Toptle automatically detects the type of command you're running and adapts accordingly:

- **Interactive applications** use full PTY mode with terminal size forwarding and title interception
- **Non-interactive commands** use efficient direct piping with proactive title updates

Your terminal title will display resource stats like `📊 5.2% CPU, 45.1MB RAM` or preserve existing titles with `Original Title | 📊 5.2% CPU, 45.1MB RAM`.

## Installation

**Via Nix flake:**
```bash
nix profile install github:YPares/toptle
# or run directly:
nix run github:YPares/toptle -- vim myfile.txt
```

**From source:**
```bash
git clone https://github.com/YPares/toptle.git && cd toptle
pip install -e .
```

## Usage

```bash
toptle [OPTIONS] -- COMMAND [ARGS...]
```

**Options:**
- `--interval SECONDS` - Update interval in seconds (default: 2.0)
- `--prefix PREFIX` - Custom prefix for resource stats (default: 📊)

**Examples:**
```bash
toptle -- vim README.md                    # Monitor editing session
toptle --interval 0.5 -- make -j4          # Watch build with fast updates
toptle --prefix "⚡" -- ./long-script.sh    # Custom prefix
```

## Features

- **Dual-mode architecture** - Automatically chooses optimal monitoring approach
- **Title interception** - Preserves and enhances existing terminal title changes
- **Process tree monitoring** - Tracks resource usage of parent process and all children
- **Terminal transparency** - Proper window size forwarding, raw terminal mode support
- **SIGWINCH handling** - Terminal resize events work correctly in interactive apps

## Performance

- **Non-interactive commands**: ~0% CPU overhead (direct subprocess piping)
- **Interactive applications**: ~1-2% CPU overhead (optimized PTY handling)
- **Memory usage**: ~16MB
- **Zero interference** with wrapped processes

## Testing

```bash
cd tests/
../toptle.py --interval 1 -- ./test_title_changes.sh    # Test title interception
../toptle.py --interval 1 -- ./test_child_processes.sh  # Test process monitoring
python3 measure_wrapper_overhead.py                     # Performance verification
```

## Implementation notes

The tool uses different strategies based on command classification:
- PTY mode handles interactive applications that need terminal control
- Direct piping mode provides zero-overhead monitoring for simple commands
- Title sequence interception preserves application-set titles
- Proactive title updates ensure monitoring visibility for non-title-setting apps

## Limitations

- Requires Python 3.8+ and the `psutil` library
- Title display depends on terminal emulator support for ANSI escape sequences
- PTY mode introduces minimal overhead for interactive applications
- Process tree detection may miss processes that detach from the parent

## License

MIT
