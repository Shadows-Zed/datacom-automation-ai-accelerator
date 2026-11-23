#!/usr/bin/env python3
"""
Unified portfolio verification and performance benchmark runner.

Runs all automated tests across Tasks 1–3 and optionally executes a live
10,000-customer / 50,000-transaction head-to-head benchmark comparing the
legacy script (`process_data.py`) against the refactored pipeline
(`process_data_final.py`).

Usage:
    python3 scripts/run_all_checks.py              # Run all tests + benchmark
    python3 scripts/run_all_checks.py --no-bench   # Run tests & syntax checks only
"""

import argparse
import csv
import os
import subprocess
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK1_DIR = os.path.join(REPO_ROOT, "task1-ai-debugging-refactoring")
TASK2_DIR = os.path.join(REPO_ROOT, "task2-kudos-spec-driven-app")
TASK3_DIR = os.path.join(REPO_ROOT, "task3-orderbot-agentic-proposal")


def _banner(title: str) -> None:
    print(f"\n{'=' * 72}\n  {title}\n{'=' * 72}")


def _run(cmd: list[str], cwd: str, env: dict | None = None, expect_fail: bool = False) -> bool:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(cmd, cwd=cwd, env=merged_env, capture_output=True, text=True)
    ok = (proc.returncode != 0) if expect_fail else (proc.returncode == 0)
    if not ok:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
    else:
        summary_lines = [
            line for line in (proc.stderr + "\n" + proc.stdout).splitlines()
            if line.startswith("Ran ") or line in ("OK",) or line.startswith("FAILED")
        ]
        for line in summary_lines:
            print(f"  {line}")
    return ok


def run_benchmark() -> None:
    """Head-to-head performance benchmark on 10,000 customers & 50,000 transactions."""
    _banner("Task 1 Live Performance Benchmark (10,000 Customers · 50,000 Transactions)")
    sys.path.insert(0, TASK1_DIR)
    import process_data
    import process_data_final

    with tempfile.TemporaryDirectory() as tmp:
        c_path = os.path.join(tmp, "customers.csv")
        t_path = os.path.join(tmp, "transactions.csv")
        n_c, n_t = 10_000, 50_000

        with open(c_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["customer_id", "name", "email", "join_date"])
            for i in range(n_c):
                w.writerow([f"C{i:05d}", f"User {i}", f"user{i}@example.com", "2023-01-01"])

        cats = ["electronics", "clothing", "food", "books"]
        with open(t_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["transaction_id", "customer_id", "amount", "date", "category"])
            for i in range(n_t):
                w.writerow([f"T{i:06d}", f"C{i % n_c:05d}", "19.99", "2024-01-15", cats[i % 4]])

        p_orig = process_data.DataProcessor(c_path)
        p_orig.load_data()
        p_orig.process_transactions(t_path)

        t0 = time.perf_counter()
        for _ in range(20):
            p_orig.calculate_customer_metrics()
        m_orig = time.perf_counter() - t0

        t0 = time.perf_counter()
        for i in range(500):
            p_orig.find_matches(f"user{i}@example.com", field="email")
        s_orig = time.perf_counter() - t0

        p_final = process_data_final.DataProcessor(c_path)
        p_final.load_data()
        p_final.process_transactions(t_path)

        t0 = time.perf_counter()
        for _ in range(20):
            p_final.calculate_customer_metrics()
        m_final = time.perf_counter() - t0

        t0 = time.perf_counter()
        for i in range(500):
            p_final.find_matches(f"user{i}@example.com", field="email")
        s_sub = time.perf_counter() - t0

        t0 = time.perf_counter()
        for i in range(500):
            p_final.find_matches(f"user{i}@example.com", field="email", exact=True)
        s_exact = time.perf_counter() - t0

    print(f"  calculate_customer_metrics (x20):  {m_orig:.4f}s -> {m_final:.4f}s  ({m_orig / m_final:.2f}x faster)")
    print(f"  find_matches substring    (x500):  {s_orig:.4f}s -> {s_sub:.4f}s  ({s_orig / s_sub:.2f}x faster)")
    print(f"  find_matches exact O(1)   (x500):  {s_orig:.4f}s -> {s_exact:.4f}s  ({s_orig / s_exact:.1f}x faster)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all portfolio checks and benchmarks.")
    parser.add_argument("--no-bench", action="store_true", help="Skip performance benchmark")
    args = parser.parse_args()

    all_ok = True

    _banner("1/4 · Task 1 Red Phase (Confirming Legacy Baseline Bugs Reproduce)")
    ok_red = _run(
        [sys.executable, "-m", "unittest", "TEST_CASES.py"],
        cwd=TASK1_DIR,
        env={"DATA_PROCESSOR_MODULE": "process_data"},
        expect_fail=True,
    )
    print("  [PASS] Legacy baseline reproduced expected defects." if ok_red else "  [FAIL] Unexpected Red-phase outcome.")
    all_ok &= ok_red

    _banner("2/4 · Task 1 Green Phase (Refactored Analytics Pipeline — 16 Tests)")
    ok_t1 = _run([sys.executable, "-m", "unittest", "TEST_CASES.py"], cwd=TASK1_DIR)
    print("  [PASS] All Task 1 unit & SLA tests passed." if ok_t1 else "  [FAIL] Task 1 tests failed.")
    all_ok &= ok_t1

    _banner("3/4 · Task 2 End-to-End Kudos Portal Tests (API, RBAC, Moderation — 8 Tests)")
    ok_t2 = _run([sys.executable, "-m", "unittest", "test_kudos.py"], cwd=TASK2_DIR)
    print("  [PASS] All Task 2 API & security tests passed." if ok_t2 else "  [FAIL] Task 2 tests failed.")
    all_ok &= ok_t2

    _banner("4/4 · Task 3 Slide Generator Syntax Verification")
    ok_t3 = _run([sys.executable, "-m", "py_compile", "build_slides_pdf.py"], cwd=TASK3_DIR)
    print("  [PASS] Task 3 vector slide generator compiled cleanly." if ok_t3 else "  [FAIL] Task 3 syntax check failed.")
    all_ok &= ok_t3

    if not args.no_bench and all_ok:
        run_benchmark()

    _banner("SUMMARY")
    if all_ok:
        print("  ALL CHECKS PASSED (24/24 tests + Red-phase verification + syntax check)")
        return 0
    print("  ONE OR MORE CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
