#!/usr/bin/env python3
"""SteaMidra comprehensive test runner. Runs all tests and prints a report."""
import subprocess
import sys
import time
from pathlib import Path


def run_tests():
    root = Path(__file__).resolve().parent
    tests_dir = root / "tests"

    if not tests_dir.exists():
        print("ERROR: tests/ directory not found")
        return 1

    print("=" * 70)
    print("  SteaMidra Comprehensive Test Suite")
    print("=" * 70)
    print()

    args = [
        sys.executable, "-m", "pytest",
        str(tests_dir),
        "-v",
        "--tb=short",
        "--color=yes",
        "-p", "no:cacheprovider",
        "--no-header",
        "-r", "a",
    ]

    start = time.monotonic()
    result = subprocess.run(args, cwd=str(root))
    elapsed = time.monotonic() - start

    print()
    print("=" * 70)
    if result.returncode == 0:
        print(f"  ALL TESTS PASSED  ({elapsed:.2f}s)")
    else:
        print(f"  SOME TESTS FAILED  ({elapsed:.2f}s)")
        print(f"  Exit code: {result.returncode}")
    print("=" * 70)

    return result.returncode


if __name__ == "__main__":
    sys.exit(run_tests())
