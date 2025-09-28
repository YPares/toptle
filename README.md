# Toptle 🐢

A transparent process monitor that displays real-time resource stats in your
terminal title.

Your terminal title shows: `ORIGINAL_TITLE 🐢5.2% CPU, 45.1MB RAM🐢`

## Installation

**Via Nix flake:**

```bash
nix profile install github:YPares/toptle
# or run directly:
nix run github:YPares/toptle -- <command>
```

**Directly run via uvx:**

```bash
uvx toptle
```

**From source:**

```bash
git clone https://github.com/YPares/toptle.git && cd toptle
uv run toptle
# Or install with pip:
pip install -e .
```

## Usage

```bash
toptle [OPTIONS] [--] COMMAND [ARGS...]
```

**Options:**

- `--refresh`, `-r` - Update interval in seconds (default: 2.0)
- `--metrics`, `-m` - Display: cpu,ram,disk,files,threads,procs,all (default:
  cpu,ram)
- `--pty`, `-p` - PTY mode for edge cases

**Examples:**

```bash
toptle python -m http.server 8000  # Basic usage
toptle -r 0.5 make -j4             # Faster updates  
toptle -m all ./build-script.sh    # All metrics
toptle --pty special-app           # PTY mode if needed
```

## Features

- **Customizable metrics** - CPU, RAM, disk I/O, file descriptors, threads,
  process count
- **Process tree monitoring** - Tracks parent and all child processes
- **Title interception** - Captures and combines with app titles (requires
  `--pty`)

## Modes

- **Default**: Direct mode - zero overhead but will ignore title sequence(s) sent
  by application
- **`--pty`**: PTY mode - full title interception. Might also be needed by
  certain apps to work properly

## Limitations

- Title display depends on terminal emulator support for ANSI escape sequences
- Process tree detection may miss processes that detach from the parent
