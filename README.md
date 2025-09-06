# Toptle 🐢

A transparent process monitor that displays real-time resource stats in your terminal title.

Your terminal title shows: `ORIGINAL_TITLE | 📊 5.2% CPU, 45.1MB RAM`

## Installation

**Via Nix flake:**
```bash
nix profile install github:YPares/toptle
# or run directly:
nix run github:YPares/toptle -- <command>
```

**From source:**
```bash
git clone https://github.com/YPares/toptle.git && cd toptle
pip install -e .
```

## Usage

```bash
toptle [OPTIONS] [--] COMMAND [ARGS...]
```

**Options:**
- `--refresh`, `-r` - Update interval in seconds (default: 2.0)
- `--metrics`, `-m` - Display: cpu,ram,disk,files,threads,procs,all (default: cpu,ram)  
- `--pty`, `-t` - PTY mode for edge cases (rarely needed)

**Examples:**
```bash
toptle -- python -m http.server 8000    # Basic usage
toptle -r 0.5 -- make -j4                # Fast updates  
toptle -m all -- ./build-script.sh       # All metrics
toptle --pty -- special-app               # PTY mode if needed
```

## Features

- **Zero interference** - Works transparently with any command
- **Customizable metrics** - CPU, RAM, disk I/O, file descriptors, threads, process count
- **Process tree monitoring** - Tracks parent and all child processes  
- **Title interception** - Captures and combines with app titles (requires `--pty`)

## Metrics

**Available**: cpu, ram, disk, files, threads, procs  
**Examples**: `📊 CPU:5.2% RAM:45MB` • `📊 CPU:5.2% RAM:45MB Disk:↑12 ↓8KB/s Procs:8`

## Modes

- **Default**: Direct mode - zero overhead but will ignore title sequence sent by application
- **`--pty`**: PTY mode - full title interception. Might also be needed by certain apps to work properly

## Requirements

Python 3.8+ and `psutil`

## Limitations

- Title display depends on terminal emulator support for ANSI escape sequences
- Process tree detection may miss processes that detach from the parent

## License

MIT
