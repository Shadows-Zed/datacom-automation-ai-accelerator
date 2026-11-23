#!/usr/bin/env python3
"""
Unit tests for Datacom Customer Analytics Data Processor.

Supports testing either the refactored implementation (`process_data_final`, default)
or the original legacy script (`process_data`) to verify bug reproduction before the fix:

    # Reproduce bugs against original script (expected to fail):
    DATA_PROCESSOR_MODULE=process_data python3 -m unittest -v TEST_CASES.py

    # Verify all fixes against refactored script (expected to pass):
    python3 -m unittest -v TEST_CASES.py
"""

import csv
import importlib
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

TARGET_MODULE_NAME = os.environ.get("DATA_PROCESSOR_MODULE", "process_data_final")
target_module = importlib.import_module(TARGET_MODULE_NAME)
DataProcessor = target_module.DataProcessor


class BaseProcessorTest(unittest.TestCase):
    """Shared fixtures using temporary directories for isolated I/O testing."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.customers_path = os.path.join(self.temp_dir.name, "customers.csv")
        self.transactions_path = os.path.join(self.temp_dir.name, "transactions.csv")

        with open(self.customers_path, "w", encoding="utf-8", newline="") as f:
            f.write(
                "customer_id,name,email,join_date\n"
                "C001,John Smith,john.smith@email.com,2023-01-15\n"
                "C002,Jane Doe,jane.doe@email.com,2023-02-20\n"
                "C003,Bob Johnson,bob.johnson@email.com,2023-03-10\n"
                "C004,Alice Brown,alice.brown@email.com,2023-04-05\n"
                "C005,Charlie Wilson,charlie.wilson@email.com,2023-05-12 \n"
            )

        with open(self.transactions_path, "w", encoding="utf-8", newline="") as f:
            f.write(
                "transaction_id,customer_id,amount,date,category\n"
                "T001,C001,150.50,2024-01-10,electronics\n"
                "T002,C002,75.25,2024-01-11,clothing\n"
                "T003,C001,200.00,2024-01-12,electronics\n"
                "T004,C003,45.75,2024-01-13,food\n"
                "T005,C002,120.00,2024-01-14,clothing\n"
                "T006,C004,89.99,2024-01-15,books\n"
                "T007,C005,300.00,2024-01-16,electronics\n"
                "T008,C001,25.50,2024-01-17,food\n"
                "T009,C003,180.00,2024-01-18,clothing\n"
                "T010,C002,95.25,2024-01-19,books \n"
            )

    def tearDown(self):
        self.temp_dir.cleanup()


class TestExportCustomerDataBugs(BaseProcessorTest):
    """Tests reproducing and verifying fixes for the export bugs seen in error.log."""

    def test_export_csv_handles_corrupted_non_dict_customer_record(self):
        """
        Reproduces the AttributeError pattern from error.log:
        `next(iter(self.customers.values())).keys()` crashes if the first
        customer value is malformed (not a dict).
        """
        processor = DataProcessor(self.customers_path)
        processor.customers = {
            "C_BAD": None,
            "C001": {
                "name": "John Smith",
                "email": "john.smith@email.com",
                "join_date": "2023-01-15",
                "total_spent": 100.0,
                "transaction_count": 1,
            },
        }
        output_csv = os.path.join(self.temp_dir.name, "export_corrupted.csv")

        result = processor.export_customer_data(output_csv, "csv")

        self.assertTrue(result, "Export should skip malformed records instead of crashing on .keys()")
        with open(output_csv, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["customer_id"], "C001")

    def test_export_csv_handles_heterogeneous_customer_keys(self):
        """
        Original code only inspects the first customer's keys, causing csv.DictWriter
        to raise ValueError if a subsequent customer record contains extra keys.
        """
        processor = DataProcessor(self.customers_path)
        processor.customers = {
            "C001": {
                "name": "John Smith",
                "email": "john.smith@email.com",
                "join_date": "2023-01-15",
                "total_spent": 100.0,
                "transaction_count": 1,
            },
            "C002": {
                "name": "Jane Doe",
                "email": "jane.doe@email.com",
                "join_date": "2023-02-20",
                "total_spent": 200.0,
                "transaction_count": 2,
                "loyalty_tier": "gold",
            },
        }
        output_csv = os.path.join(self.temp_dir.name, "export_heterogeneous.csv")

        result = processor.export_customer_data(output_csv, "csv")

        self.assertTrue(result, "Export should handle varying customer schemas cleanly")
        with open(output_csv, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            self.assertIn("loyalty_tier", reader.fieldnames)
            rows = list(reader)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["loyalty_tier"], "gold")

    def test_export_csv_empty_customers_writes_headers(self):
        """Empty customer dataset should still produce a valid CSV with header columns."""
        processor = DataProcessor(self.customers_path)
        output_csv = os.path.join(self.temp_dir.name, "export_empty.csv")

        result = processor.export_customer_data(output_csv, "csv")

        self.assertTrue(result)
        with open(output_csv, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            self.assertIsNotNone(reader.fieldnames)
            self.assertIn("customer_id", reader.fieldnames)
            self.assertEqual(list(reader), [])

    def test_export_format_case_insensitive_and_invalid_rejected(self):
        """Export format should handle uppercase ('CSV', 'JSON') and reject invalid formats."""
        processor = DataProcessor(self.customers_path)
        processor.load_data()

        csv_out = os.path.join(self.temp_dir.name, "upper.csv")
        json_out = os.path.join(self.temp_dir.name, "upper.json")
        bad_out = os.path.join(self.temp_dir.name, "bad.xml")

        self.assertTrue(processor.export_customer_data(csv_out, "CSV"))
        self.assertTrue(processor.export_customer_data(json_out, "JSON"))
        self.assertFalse(processor.export_customer_data(bad_out, "xml"))


class TestDataLoadingAndSanitization(BaseProcessorTest):
    """Tests for CSV loading, whitespace trimming, and malformed-row resilience."""

    def test_load_data_strips_trailing_whitespace(self):
        """Sample customers.csv has a trailing space on C005's join_date ('2023-05-12 ')."""
        processor = DataProcessor(self.customers_path)
        self.assertTrue(processor.load_data())
        self.assertEqual(processor.customers["C005"]["join_date"], "2023-05-12")

    def test_load_data_missing_file_returns_false(self):
        """Missing input CSV should return False cleanly without raising."""
        processor = DataProcessor(os.path.join(self.temp_dir.name, "nonexistent.csv"))
        self.assertFalse(processor.load_data())

    def test_process_transactions_strips_category_whitespace(self):
        """
        Sample transactions.csv has 'books' (T006) and 'books ' (T010).
        They must normalize to a single 'books' category with count 2.
        """
        processor = DataProcessor(self.customers_path)
        processor.load_data()
        processor.process_transactions(self.transactions_path)

        metrics = processor.calculate_customer_metrics()
        self.assertEqual(metrics["category_breakdown"].get("books"), 2)
        self.assertNotIn("books ", metrics["category_breakdown"])

    def test_process_transactions_skips_malformed_amount_without_aborting(self):
        """A single corrupted numeric amount should be skipped rather than aborting the entire batch."""
        bad_tx_path = os.path.join(self.temp_dir.name, "bad_transactions.csv")
        with open(bad_tx_path, "w", encoding="utf-8", newline="") as f:
            f.write(
                "transaction_id,customer_id,amount,date,category\n"
                "T001,C001,100.00,2024-01-10,electronics\n"
                "T002,C001,NOT_A_NUMBER,2024-01-11,electronics\n"
                "T003,C002,50.00,2024-01-12,books\n"
            )

        processor = DataProcessor(self.customers_path)
        processor.load_data()
        result = processor.process_transactions(bad_tx_path)

        self.assertTrue(result)
        self.assertEqual(len(processor.transactions), 2)
        self.assertAlmostEqual(processor.customers["C001"]["total_spent"], 100.00, places=2)
        self.assertAlmostEqual(processor.customers["C002"]["total_spent"], 50.00, places=2)


class TestMetricsAndReportingAccuracy(BaseProcessorTest):
    """Tests for metric accuracy, floating-point precision, and complete reports."""

    def test_metrics_consistency_with_unknown_customer_transactions(self):
        """
        Transactions belonging to unknown customers must not skew
        average_transaction_value (total_revenue / total_transactions).
        """
        tx_with_unknown = os.path.join(self.temp_dir.name, "unknown_tx.csv")
        with open(tx_with_unknown, "w", encoding="utf-8", newline="") as f:
            f.write(
                "transaction_id,customer_id,amount,date,category\n"
                "T001,C001,100.00,2024-01-10,electronics\n"
                "T002,C999,500.00,2024-01-11,electronics\n"
            )

        processor = DataProcessor(self.customers_path)
        processor.load_data()
        processor.process_transactions(tx_with_unknown)
        metrics = processor.calculate_customer_metrics()

        self.assertEqual(metrics["total_transactions"], 1)
        self.assertAlmostEqual(metrics["total_revenue"], 100.00, places=2)
        self.assertAlmostEqual(metrics["average_transaction_value"], 100.00, places=2)

    def test_customer_summary_report_includes_customer_id(self):
        """customer_summary report must retain customer_id on every customer record."""
        processor = DataProcessor(self.customers_path)
        processor.load_data()
        processor.process_transactions(self.transactions_path)

        report_path = os.path.join(self.temp_dir.name, "customer_summary.json")
        self.assertTrue(processor.generate_report("customer_summary", report_path))

        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        self.assertEqual(len(report["customers"]), 5)
        for customer in report["customers"]:
            self.assertIn("customer_id", customer)

    def test_financial_precision_avoids_float_drift(self):
        """Adding 0.10 + 0.20 should equal 0.30, not 0.30000000000000004."""
        drift_tx = os.path.join(self.temp_dir.name, "drift_tx.csv")
        with open(drift_tx, "w", encoding="utf-8", newline="") as f:
            f.write(
                "transaction_id,customer_id,amount,date,category\n"
                "T001,C001,0.10,2024-01-10,food\n"
                "T002,C001,0.20,2024-01-11,food\n"
            )

        processor = DataProcessor(self.customers_path)
        processor.load_data()
        processor.process_transactions(drift_tx)
        metrics = processor.calculate_customer_metrics()

        self.assertEqual(processor.customers["C001"]["total_spent"], 0.3)
        self.assertEqual(metrics["total_revenue"], 0.3)

    def test_top_customers_limited_to_10_descending(self):
        """top_customers should return at most 10 customers ordered by total_spent desc."""
        large_cust = os.path.join(self.temp_dir.name, "many_customers.csv")
        with open(large_cust, "w", encoding="utf-8", newline="") as f:
            f.write("customer_id,name,email,join_date\n")
            for i in range(1, 26):
                f.write(f"C{i:03d},Customer {i},c{i}@email.com,2023-01-01\n")

        processor = DataProcessor(large_cust)
        processor.load_data()
        for i in range(1, 26):
            processor.customers[f"C{i:03d}"]["total_spent"] = float(i * 10)

        metrics = processor.calculate_customer_metrics()
        top = metrics["top_customers"]
        self.assertEqual(len(top), 10)
        self.assertEqual(top[0][0], "C025")
        self.assertEqual(top[-1][0], "C016")


class TestFindMatchesAndPerformance(BaseProcessorTest):
    """Tests for search correctness and algorithmic performance."""

    def test_find_matches_by_name_case_insensitive(self):
        processor = DataProcessor(self.customers_path)
        processor.load_data()
        matches = processor.find_matches("smith", field="name")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["customer_id"], "C001")

    def test_find_matches_by_customer_id(self):
        """Searching by field='customer_id' should locate matching customers."""
        processor = DataProcessor(self.customers_path)
        processor.load_data()
        matches = processor.find_matches("C003", field="customer_id")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["name"], "Bob Johnson")

    def test_performance_large_dataset_meets_sla(self):
        """
        Stress test: 5,000 customers, 25,000 transactions, metric calculation,
        and 500 exact/indexed lookups should complete well within SLA (< 2.0s).
        """
        num_customers = 5000
        num_transactions = 25000
        large_cust = os.path.join(self.temp_dir.name, "perf_customers.csv")
        large_tx = os.path.join(self.temp_dir.name, "perf_transactions.csv")

        with open(large_cust, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["customer_id", "name", "email", "join_date"])
            for i in range(num_customers):
                writer.writerow([f"C{i:05d}", f"User {i}", f"user{i}@example.com", "2023-01-01"])

        categories = ["electronics", "clothing", "food", "books"]
        with open(large_tx, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["transaction_id", "customer_id", "amount", "date", "category"])
            for i in range(num_transactions):
                cid = f"C{i % num_customers:05d}"
                writer.writerow([f"T{i:06d}", cid, "19.99", "2024-01-15", categories[i % 4]])

        start = time.perf_counter()
        processor = DataProcessor(large_cust)
        self.assertTrue(processor.load_data())
        self.assertTrue(processor.process_transactions(large_tx))
        metrics = processor.calculate_customer_metrics()
        for i in range(500):
            found = processor.find_matches(f"C{i:05d}", field="customer_id")
            self.assertEqual(len(found), 1)
        elapsed = time.perf_counter() - start

        self.assertEqual(metrics["total_customers"], num_customers)
        self.assertEqual(metrics["total_transactions"], num_transactions)
        self.assertLess(elapsed, 2.0, f"Pipeline exceeded SLA target: {elapsed:.3f}s")


class TestPipelineErrorHandling(BaseProcessorTest):
    """Tests that main() does not falsely log success when downstream steps fail."""

    def test_main_does_not_report_success_when_export_fails(self):
        """
        Reproduces error.log line 8: even after export_customer_data failed,
        original main() still logged 'Data processing completed successfully'.
        """
        with patch.object(DataProcessor, "load_data", return_value=True), \
             patch.object(DataProcessor, "process_transactions", return_value=True), \
             patch.object(DataProcessor, "generate_report", return_value=True), \
             patch.object(DataProcessor, "export_customer_data", return_value=False), \
             patch.object(target_module.logger, "info") as mock_info:
            result = target_module.main()

            logged_messages = [call.args[0] for call in mock_info.call_args_list if call.args]
            self.assertNotIn(
                "Data processing completed successfully",
                logged_messages,
                "main() must not log success when an export step fails",
            )
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
