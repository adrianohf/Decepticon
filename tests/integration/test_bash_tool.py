"""
Integration test for the bash tool with Docker sandbox.

Prerequisites:
    - Docker must be running
    - Run: docker compose up -d sandbox
    - The sandbox container must be named 'decepticon-sandbox'

Usage:
    pytest tests/integration/test_bash_tool.py -v
    or:
    python tests/integration/test_bash_tool.py
"""

import subprocess
import time
import sys
import os

# Add root directory to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# ─── Setup: Ensure sandbox is running ────────────────────────────────────

def ensure_sandbox_running():
    """Check if sandbox container is running, start it if not."""
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "decepticon-sandbox"],
        capture_output=True, text=True
    )
    if result.returncode != 0 or "true" not in result.stdout:
        print("🔧 Starting sandbox container...")
        subprocess.run(
            ["docker", "compose", "up", "-d", "--build", "sandbox"],
            cwd=".",
            check=True
        )
        # Wait for container to be ready
        time.sleep(3)
        print("✅ Sandbox started")
    else:
        print("✅ Sandbox already running")


# ─── Tests ───────────────────────────────────────────────────────────────

def test_basic_command():
    """Test: simple 'ls /' command should complete with exit_code=0."""
    from decepticon.tools.bash.tool import bash, _managers, TmuxSessionManager
    
    # Clear cached managers to start fresh
    _managers.clear()
    TmuxSessionManager._initialized.clear()
    
    result = bash.invoke({"command": "ls /"})
    print(f"\n📋 test_basic_command:\n{result[:500]}")
    
    assert "[COMPLETED]" in result, f"Expected [COMPLETED], got: {result[:200]}"
    assert "exit_code=0" in result, f"Expected exit_code=0, got: {result[:200]}"
    # Common root directories should be present
    assert "usr" in result, f"Expected 'usr' in ls output, got: {result[:200]}"
    assert "etc" in result, f"Expected 'etc' in ls output, got: {result[:200]}"
    print("✅ PASSED")


def test_command_with_exit_code():
    """Test: a failing command should return non-zero exit code."""
    from decepticon.tools.bash.tool import bash
    
    result = bash.invoke({"command": "ls /nonexistent_dir_12345"})
    print(f"\n📋 test_command_with_exit_code:\n{result[:500]}")
    
    assert "[COMPLETED]" in result, f"Expected [COMPLETED], got: {result[:200]}"
    # ls on non-existent dir returns exit code 2
    assert "exit_code=0" not in result, f"Expected non-zero exit code, got: {result[:200]}"
    print("✅ PASSED")


def test_whoami():
    """Test: whoami should return the sandbox user."""
    from decepticon.tools.bash.tool import bash
    
    result = bash.invoke({"command": "whoami"})
    print(f"\n📋 test_whoami:\n{result[:500]}")
    
    assert "[COMPLETED]" in result
    assert "decepticon_agent" in result, f"Expected 'decepticon_agent', got: {result[:200]}"
    print("✅ PASSED")


def test_cwd_tracking():
    """Test: cd should update the reported cwd."""
    from decepticon.tools.bash.tool import bash
    
    # cd to /tmp and check cwd
    result = bash.invoke({"command": "cd /tmp && pwd"})
    print(f"\n📋 test_cwd_tracking:\n{result[:500]}")
    
    assert "[COMPLETED]" in result
    assert "/tmp" in result, f"Expected '/tmp' in output, got: {result[:200]}"
    print("✅ PASSED")


def test_empty_command_reads_screen():
    """Test: calling bash() with no command should read current screen."""
    from decepticon.tools.bash.tool import bash
    
    result = bash.invoke({})
    print(f"\n📋 test_empty_command_reads_screen:\n{result[:500]}")
    
    # Should return IDLE or RUNNING status
    assert "[IDLE]" in result or "[RUNNING]" in result or "[UNKNOWN]" in result, \
        f"Expected status marker, got: {result[:200]}"
    print("✅ PASSED")


def test_multiline_output():
    """Test: command with multi-line output should capture all lines."""
    from decepticon.tools.bash.tool import bash
    
    result = bash.invoke({"command": "echo 'line1'; echo 'line2'; echo 'line3'"})
    print(f"\n📋 test_multiline_output:\n{result[:500]}")
    
    assert "[COMPLETED]" in result
    assert "line1" in result
    assert "line2" in result
    assert "line3" in result
    print("✅ PASSED")


def test_parallel_sessions():
    """Test: different sessions should be independent."""
    from decepticon.tools.bash.tool import bash, _managers, TmuxSessionManager
    
    # Run in session "test-a"
    result_a = bash.invoke({
        "command": "echo 'session-a-output'",
        "session": "test-a"
    })
    print(f"\n📋 test_parallel_sessions (A):\n{result_a[:300]}")
    
    # Run in session "test-b"
    result_b = bash.invoke({
        "command": "echo 'session-b-output'",
        "session": "test-b"
    })
    print(f"\n📋 test_parallel_sessions (B):\n{result_b[:300]}")
    
    assert "session-a-output" in result_a
    assert "session-b-output" in result_b
    # Cross-contamination check
    assert "session-b-output" not in result_a
    assert "session-a-output" not in result_b
    print("✅ PASSED")


# ─── Runner ──────────────────────────────────────────────────────────────

def main():
    """Run all tests sequentially."""
    print("=" * 60)
    print("  Bash Tool Integration Tests")
    print("=" * 60)
    
    ensure_sandbox_running()
    
    tests = [
        test_basic_command,
        test_command_with_exit_code,
        test_whoami,
        test_cwd_tracking,
        test_empty_command_reads_screen,
        test_multiline_output,
        test_parallel_sessions,
    ]
    
    passed = 0
    failed = 0
    
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"❌ FAILED: {test_fn.__name__}: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
