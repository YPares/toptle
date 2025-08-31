#!/usr/bin/env python3
"""
Test script to verify the improvements made to toptle
"""

import subprocess
import time
import sys
import os


def test_basic_command():
    """Test with a basic non-interactive command"""
    print("=== Testing with basic command ===")
    cmd = ["../toptle.py", "--interval", "0.5", "--", "sleep", "3"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"Exit code: {result.returncode}")
    print(f"Output preview: {result.stdout[:200]}...")
    return result.returncode == 0


def test_interactive_preparation():
    """Prepare for interactive testing"""
    print("\n=== Interactive Testing Instructions ===")
    print("To test vim interactively:")
    print("1. Run: ../toptle.py --interval 1 -- vim test_vim.txt")
    print("2. Check if:")
    print("   - Terminal title shows resource usage")
    print("   - Vim displays correctly with full terminal size")
    print("   - All vim commands work normally (arrow keys, :q, etc.)")
    print("   - Terminal window resizing works properly")
    print("3. To test terminal size, try resizing your terminal window")
    print("4. Exit vim with :q")

    print("\nTo test other applications:")
    print("- htop: ../toptle.py -- htop")
    print("- less: ../toptle.py -- less test_vim.txt")

    return True


def verify_implementation():
    """Check if the key improvements are in place"""
    print("\n=== Verifying Implementation ===")

    # Check if the file has been modified with our improvements
    with open("../toptle.py", "r") as f:
        content = f.read()

    improvements = {
        "Terminal size functions": "get_terminal_size" in content
        and "set_pty_size" in content,
        "SIGWINCH handling": "handle_window_size_change" in content
        and "SIGWINCH" in content,
        "Raw terminal mode": "setup_raw_terminal" in content
        and "restore_terminal" in content,
        "Proactive title updates": "send_proactive_title_update" in content,
        "Enhanced imports": "import termios" in content and "import fcntl" in content,
    }

    print("Implementation status:")
    for feature, implemented in improvements.items():
        status = "✅ IMPLEMENTED" if implemented else "❌ MISSING"
        print(f"  {feature}: {status}")

    all_implemented = all(improvements.values())
    return all_implemented


if __name__ == "__main__":
    print("Testing Process Monitor Improvements")
    print("=" * 40)

    # Verify implementation
    implementation_ok = verify_implementation()
    if not implementation_ok:
        print("\n❌ Some improvements are missing!")
        sys.exit(1)

    # Test basic functionality
    basic_test_ok = test_basic_command()
    if not basic_test_ok:
        print("\n❌ Basic functionality test failed!")
        sys.exit(1)

    # Show interactive testing instructions
    test_interactive_preparation()

    print("\n✅ All automated tests passed!")
    print("✅ Implementation verified!")
    print("📋 Follow the interactive testing instructions above to complete testing.")
