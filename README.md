# 🐢 Toptle

> Like a turtle carrying its shell, **toptle** carries resource stats in your terminal title.

**Toptle** is a transparent process monitor that displays real-time CPU and memory usage in your terminal title bar. It works seamlessly with both interactive applications (vim, htop) and command-line tools (make, git) without interfering with their operation.

## ✨ Features

- **📊 Real-time resource monitoring** - CPU percentage and memory usage
- **🎯 Terminal title integration** - Stats appear in your terminal title bar
- **🔄 Title interception** - Preserves and enhances existing title changes
- **⚡ Dual-mode architecture**:
  - **Interactive mode**: Full PTY support for vim, htop, etc.
  - **Non-interactive mode**: Lightweight direct piping for simple commands
- **🪟 Terminal transparency** - Proper window size forwarding and raw terminal mode
- **📈 Process tree monitoring** - Tracks parent process and all children

## 🚀 Quick Start

```bash
# Basic usage
toptle vim myfile.txt

# Custom update interval  
toptle --interval 1 -- make build

# Custom prefix
toptle --prefix "🔥" -- htop
```

## 📦 Installation

### Requirements
- Python 3.6+
- `psutil` library

```bash
pip install psutil
```

### Usage
```bash
toptle [OPTIONS] -- COMMAND [ARGS...]
```

**Options:**
- `--interval SECONDS` - Update interval (default: 2.0)
- `--prefix PREFIX` - Title prefix (default: 📊)

## 💡 How It Works

Toptle automatically detects whether your command needs full terminal support:

- **Interactive applications** (vim, less, htop, bash scripts) → Full PTY mode with title interception
- **Simple commands** (sleep, echo, make, git) → Efficient direct piping with proactive title updates

## 📋 Examples

```bash
# Monitor vim editing
toptle -- vim README.md

# Watch build process
toptle --interval 0.5 -- make -j4

# Monitor interactive tools
toptle -- htop

# Track long-running scripts
toptle -- bash deployment.sh
```

## 🎯 What You'll See

Your terminal title will show:
- **With title interception**: `Original Title | 📊 5.2% CPU, 45.1MB RAM`
- **Proactive updates**: `📊 2.1% CPU, 23.4MB RAM`

## 🧪 Testing

Run the test suite:
```bash
cd tests/

# Test title interception
../toptle --interval 1 -- ./test_title_changes.sh

# Test process tree monitoring  
../toptle --interval 1 -- ./test_child_processes.sh

# Performance verification
python3 measure_wrapper_overhead.py
```

## ⚡ Performance

- **Non-interactive commands**: ~0% CPU overhead
- **Interactive applications**: ~1-2% CPU overhead
- **Memory usage**: ~16MB
- **Zero interference** with wrapped processes

## 🐢 Why "Toptle"?

A playful combination of "**top**" (the classic process monitor) and "**turtle**" - because like a turtle carries its protective shell, toptle carries your process statistics wherever your commands go.

## 📄 License

Open source - feel free to modify and distribute.

---

*Toptle: The gentle process monitor that sits on top of your commands and watches over them* 🐢✨
