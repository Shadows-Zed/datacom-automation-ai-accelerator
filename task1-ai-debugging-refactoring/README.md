# Task 1: AI-Powered Debugging, Testing & Performance Refactoring

> **Role:** Pilot (Conversational AI Coding with Human Oversight & Red → Green TDD)

Refactored a legacy nightly customer analytics script (`process_data.py` → `process_data_final.py`) that was failing intermittently in production and missing its SLA.

## Defects Identified & Fixed

1. **Fragile CSV Export (`error.log` root cause):** Replaced blind `next(iter(self.customers.values())).keys()` with per-record dictionary validation, deterministic canonical headers (`DEFAULT_EXPORT_FIELDS`), union-of-keys support for heterogeneous records, case-insensitive format handling, and header emission on empty datasets.
2. **Silent Failure Masking in `main()`:** Checked return statuses across every report and export call so failed runs log explicit errors and exit non-zero instead of falsely reporting `"Data processing completed successfully"`.
3. **Hidden Data-Integrity Bugs Found Empirically:**
   - Trailing whitespace in CSV inputs (`"books "` splitting categories into `"books"` and `"books "`, and `"2023-05-12 "`).
   - Unknown-customer transactions skewing `average_transaction_value` (now isolated in `self.unmatched_transactions`).
   - Binary floating-point drift (`0.10 + 0.20 = 0.30000000000000004`) fixed with `Decimal` accumulation + `math.fsum`.
   - Missing `customer_id` in `customer_summary.json` and broken `find_matches(..., field="customer_id")`.
   - Single malformed amount crashing an entire batch instead of logging and skipping safely.

## Empirical Performance Benchmark (10,000 Customers · 50,000 Transactions)

| Operation | Legacy (`process_data.py`) | Refactored (`process_data_final.py`) | Speedup |
|---|---:|---:|---:|
| `calculate_customer_metrics()` (×20 runs) | `0.1195s` | `0.0344s` | **3.47× faster** |
| `find_matches()` substring lookup (×500) | `0.3701s` | `0.1215s` | **3.05× faster** |
| `find_matches()` exact dict lookup (×500) | `0.3701s` | `0.0024s` | **152.5× faster** |

## Quick Verification (Red → Green TDD)

```bash
# 1. Reproduce all 13 bugs against the legacy baseline script (Red)
DATA_PROCESSOR_MODULE=process_data python3 -m unittest -v TEST_CASES.py

# 2. Verify all 16 unit & SLA tests pass on the refactored script (Green)
python3 -m unittest -v TEST_CASES.py

# 3. Run end-to-end on the sample dataset
python3 process_data_final.py \
  --customers data/customers.csv \
  --transactions data/transactions.csv \
  --output-dir /tmp/kudos_analytics_out
```

See [DEBUG_LOG.md](DEBUG_LOG.md) for the complete 5-step conversational debugging log, terminal outputs, and human-in-the-loop optimization notes.
