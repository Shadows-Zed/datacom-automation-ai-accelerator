#!/usr/bin/env python3
"""
Refactored Data Processing Script for Customer Analytics.

Loads customer and transaction CSV datasets, validates and normalizes records,
computes customer analytics metrics efficiently, generates JSON reports, and
exports sanitized customer datasets in CSV or JSON format.
"""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import heapq
import json
import logging
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# Configure production-grade logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

CUSTOMER_REQUIRED_FIELDS = ("customer_id", "name", "email", "join_date")
TRANSACTION_REQUIRED_FIELDS = (
    "transaction_id",
    "customer_id",
    "amount",
    "date",
    "category",
)
DEFAULT_EXPORT_FIELDS = (
    "customer_id",
    "name",
    "email",
    "join_date",
    "total_spent",
    "transaction_count",
)
TOP_CUSTOMERS_LIMIT = 10


def _round_currency(value: Decimal) -> float:
    """Round a Decimal monetary value to 2 decimal places as a float."""
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class DataProcessor:
    """Processes customer transaction data and generates analytics reports."""

    def __init__(self, input_file: str) -> None:
        """Initialize the data processor with the customer CSV input file path."""
        self.input_file: str = input_file
        self.customers: Dict[str, Dict[str, Any]] = {}
        self.transactions: List[Dict[str, Any]] = []
        self.unmatched_transactions: List[Dict[str, Any]] = []
        self.reports: Dict[str, str] = {}

        # Internal performance structures
        self._customer_totals_decimal: Dict[str, Decimal] = {}
        self._category_counts: Counter = Counter()
        self._search_index: Dict[str, Dict[str, List[str]]] = {}
        self._indexed_customer_count: int = -1

    def _invalidate_search_index(self) -> None:
        """Clear cached field lookup indexes after customer mutations."""
        self._search_index.clear()
        self._indexed_customer_count = -1

    def _get_field_index(self, field: str) -> Dict[str, List[str]]:
        """
        Lazily build and cache a lowercase-value -> [customer_ids] dictionary index
        for O(1) exact lookups and faster repeated scans without repeated .lower() calls.
        """
        if self._indexed_customer_count != len(self.customers):
            self._search_index.clear()
            self._indexed_customer_count = len(self.customers)

        if field not in self._search_index:
            index: Dict[str, List[str]] = defaultdict(list)
            if field == "customer_id":
                for customer_id in self.customers:
                    index[str(customer_id).lower()].append(customer_id)
            else:
                for customer_id, customer_data in self.customers.items():
                    if isinstance(customer_data, dict) and field in customer_data:
                        normalized = str(customer_data[field]).lower()
                        index[normalized].append(customer_id)
            self._search_index[field] = dict(index)

        return self._search_index[field]

    def load_data(self) -> bool:
        """Load and sanitize customer records from the configured CSV file."""
        try:
            customers: Dict[str, Dict[str, Any]] = {}
            totals_decimal: Dict[str, Decimal] = {}
            skipped_rows = 0

            with open(self.input_file, "r", encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                if not reader.fieldnames:
                    logger.error(f"Input file {self.input_file} is empty or missing headers")
                    return False

                missing_cols = [
                    col for col in CUSTOMER_REQUIRED_FIELDS if col not in reader.fieldnames
                ]
                if missing_cols:
                    logger.error(
                        f"Input file {self.input_file} missing required columns: {missing_cols}"
                    )
                    return False

                for row_num, row in enumerate(reader, start=2):
                    customer_id = (row.get("customer_id") or "").strip()
                    if not customer_id:
                        skipped_rows += 1
                        logger.warning(f"Skipping customer row {row_num}: empty customer_id")
                        continue

                    if customer_id in customers:
                        logger.warning(
                            f"Duplicate customer_id '{customer_id}' at row {row_num}; "
                            "overwriting previous record"
                        )

                    customers[customer_id] = {
                        "name": (row.get("name") or "").strip(),
                        "email": (row.get("email") or "").strip(),
                        "join_date": (row.get("join_date") or "").strip(),
                        "total_spent": 0.0,
                        "transaction_count": 0,
                    }
                    totals_decimal[customer_id] = Decimal("0.00")

            self.customers = customers
            self._customer_totals_decimal = totals_decimal
            self._invalidate_search_index()

            if skipped_rows:
                logger.warning(f"Skipped {skipped_rows} malformed customer rows")
            logger.info(f"Loaded {len(self.customers)} customers")
            return True

        except FileNotFoundError:
            logger.error(f"Input file {self.input_file} not found")
            return False
        except (OSError, csv.Error) as e:
            logger.error(f"Error loading data: {e}")
            return False

    def process_transactions(self, transaction_file: str) -> bool:
        """
        Process transaction data from CSV and update matched customer records.

        Malformed rows are logged and skipped without aborting valid records.
        Transactions referencing unknown customers are logged and stored in
        `self.unmatched_transactions` so customer analytics metrics remain consistent.
        """
        try:
            processed_count = 0
            skipped_count = 0

            with open(transaction_file, "r", encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                if not reader.fieldnames:
                    logger.error(
                        f"Transaction file {transaction_file} is empty or missing headers"
                    )
                    return False

                missing_cols = [
                    col for col in TRANSACTION_REQUIRED_FIELDS if col not in reader.fieldnames
                ]
                if missing_cols:
                    logger.error(
                        f"Transaction file {transaction_file} missing required columns: "
                        f"{missing_cols}"
                    )
                    return False

                customers = self.customers
                totals_decimal = self._customer_totals_decimal
                category_counts = self._category_counts

                for row_num, row in enumerate(reader, start=2):
                    tx_id = (row.get("transaction_id") or "").strip()
                    customer_id = (row.get("customer_id") or "").strip()
                    raw_amount = (row.get("amount") or "").strip()
                    tx_date = (row.get("date") or "").strip()
                    category = (row.get("category") or "").strip()

                    if not tx_id or not customer_id or not raw_amount:
                        skipped_count += 1
                        logger.warning(
                            f"Skipping transaction row {row_num}: missing required field"
                        )
                        continue

                    try:
                        amount_decimal = Decimal(raw_amount)
                        if not amount_decimal.is_finite():
                            raise InvalidOperation("Non-finite amount")
                    except InvalidOperation:
                        skipped_count += 1
                        logger.warning(
                            f"Skipping transaction row {row_num} ({tx_id}): "
                            f"invalid amount '{raw_amount}'"
                        )
                        continue

                    amount_float = _round_currency(amount_decimal)
                    transaction = {
                        "transaction_id": tx_id,
                        "customer_id": customer_id,
                        "amount": amount_float,
                        "date": tx_date,
                        "category": category,
                    }

                    customer = customers.get(customer_id)
                    if customer is None or not isinstance(customer, dict):
                        logger.warning(f"Transaction for unknown customer: {customer_id}")
                        self.unmatched_transactions.append(transaction)
                        continue

                    # Update customer totals with exact Decimal accumulation
                    new_total = totals_decimal.get(
                        customer_id, Decimal(str(customer.get("total_spent", 0.0)))
                    ) + amount_decimal
                    totals_decimal[customer_id] = new_total
                    customer["total_spent"] = _round_currency(new_total)
                    customer["transaction_count"] = customer.get("transaction_count", 0) + 1

                    self.transactions.append(transaction)
                    category_counts[category] += 1
                    processed_count += 1

            self._invalidate_search_index()

            if skipped_count:
                logger.warning(f"Skipped {skipped_count} malformed transaction rows")
            logger.info(f"Processed {processed_count} transactions")
            return True

        except FileNotFoundError:
            logger.error(f"Transaction file {transaction_file} not found")
            return False
        except (OSError, csv.Error) as e:
            logger.error(f"Error processing transactions: {e}")
            return False

    def calculate_customer_metrics(self) -> Dict[str, Any]:
        """Calculate customer analytics metrics using efficient O(C log k) Top-K selection."""
        if not self.customers:
            logger.error("No customer data available")
            return {}

        valid_customers: List[Tuple[str, Dict[str, Any]]] = [
            (cid, data)
            for cid, data in self.customers.items()
            if isinstance(data, dict)
        ]

        total_revenue = round(
            math.fsum(float(data.get("total_spent", 0.0)) for _, data in valid_customers),
            2,
        )
        total_transactions = len(self.transactions)

        if total_transactions > 0:
            avg_tx_value = round(total_revenue / total_transactions, 2)
        else:
            avg_tx_value = 0.0

        # O(C log k) Top-K instead of O(C log C) full sort
        top_customers = heapq.nlargest(
            TOP_CUSTOMERS_LIMIT,
            valid_customers,
            key=lambda item: item[1].get("total_spent", 0.0),
        )

        # Use incremental category counter when consistent, otherwise recompute cleanly
        if sum(self._category_counts.values()) == total_transactions:
            category_breakdown = dict(self._category_counts)
        else:
            category_breakdown = dict(
                Counter(
                    str(tx.get("category", "")).strip()
                    for tx in self.transactions
                    if isinstance(tx, dict)
                )
            )

        return {
            "total_customers": len(valid_customers),
            "total_transactions": total_transactions,
            "total_revenue": total_revenue,
            "average_transaction_value": avg_tx_value,
            "top_customers": top_customers,
            "category_breakdown": category_breakdown,
        }

    def find_matches(
        self, search_term: str, field: str = "name", exact: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Find customers whose `field` matches `search_term` (case-insensitive).

        Supports `field="customer_id"` as well as any customer attribute field.
        Uses a cached dictionary index for O(1) exact lookups (when `exact=True`
        or exact `customer_id` lookup) and avoids redundant string normalization
        on repeated substring searches.
        """
        if not isinstance(search_term, str):
            return []

        search_term_lower = search_term.strip().lower()
        if not search_term_lower:
            return []

        field_index = self._get_field_index(field)
        matched_ids: List[str] = []

        if exact or (field == "customer_id" and search_term_lower in field_index):
            matched_ids = field_index.get(search_term_lower, [])
        else:
            seen = set()
            for indexed_value, customer_ids in field_index.items():
                if search_term_lower in indexed_value:
                    for cid in customer_ids:
                        if cid not in seen:
                            seen.add(cid)
                            matched_ids.append(cid)

        results: List[Dict[str, Any]] = []
        for cid in matched_ids:
            customer_data = self.customers.get(cid)
            if isinstance(customer_data, dict):
                results.append({"customer_id": cid, **customer_data})
        return results

    def generate_report(self, report_type: str, output_file: str) -> bool:
        """Generate a JSON report of the requested type and save it to `output_file`."""
        try:
            generated_at = datetime.now().isoformat()

            if report_type == "customer_summary":
                customers_list = [
                    {"customer_id": cid, **data}
                    for cid, data in self.customers.items()
                    if isinstance(data, dict)
                ]
                report_data: Dict[str, Any] = {
                    "generated_at": generated_at,
                    "customers": customers_list,
                }
            elif report_type == "metrics":
                report_data = {
                    "generated_at": generated_at,
                    "metrics": self.calculate_customer_metrics(),
                }
            elif report_type == "transactions":
                report_data = {
                    "generated_at": generated_at,
                    "transactions": self.transactions,
                }
            else:
                logger.error(f"Unknown report type: {report_type}")
                return False

            with open(output_file, "w", encoding="utf-8") as file:
                json.dump(report_data, file, indent=2)

            self.reports[report_type] = output_file
            logger.info(f"Generated {report_type} report: {output_file}")
            return True

        except (OSError, TypeError, ValueError) as e:
            logger.error(f"Error generating report: {e}")
            return False

    def export_customer_data(
        self, output_file: str, export_format: str = "csv"
    ) -> bool:
        """
        Export customer data in CSV or JSON format.

        Validates that each customer record is a dictionary before export and
        determines CSV fieldnames across all valid records so malformed entries
        or heterogeneous schemas do not crash the export.
        """
        try:
            if not isinstance(export_format, str):
                logger.error(f"Unsupported format: {export_format}")
                return False

            normalized_format = export_format.strip().lower()
            if normalized_format not in ("csv", "json"):
                logger.error(f"Unsupported format: {export_format}")
                return False

            if not isinstance(self.customers, dict):
                logger.error("Customer dataset is not a valid dictionary")
                return False

            # Validate records safely instead of calling .keys() blindly on first item
            valid_records: Dict[str, Dict[str, Any]] = {}
            for customer_id, data in self.customers.items():
                if not isinstance(data, dict):
                    logger.warning(
                        f"Skipping malformed customer record '{customer_id}': "
                        f"expected dict, got {type(data).__name__}"
                    )
                    continue
                valid_records[customer_id] = data

            if normalized_format == "csv":
                # Build deterministic union of schema columns across all valid records
                fieldnames: List[str] = list(DEFAULT_EXPORT_FIELDS)
                seen_fields = set(fieldnames)
                for data in valid_records.values():
                    for key in data.keys():
                        if key not in seen_fields:
                            seen_fields.add(key)
                            fieldnames.append(key)

                with open(output_file, "w", encoding="utf-8", newline="") as file:
                    writer = csv.DictWriter(
                        file, fieldnames=fieldnames, extrasaction="ignore"
                    )
                    writer.writeheader()
                    for customer_id, data in valid_records.items():
                        writer.writerow({"customer_id": customer_id, **data})

            else:  # json
                with open(output_file, "w", encoding="utf-8") as file:
                    json.dump(valid_records, file, indent=2)

            logger.info(f"Exported customer data to {output_file}")
            return True

        except (OSError, TypeError, ValueError, csv.Error) as e:
            logger.error(f"Error exporting data: {e}")
            return False


def main(
    customers_file: str = "customers.csv",
    transactions_file: str = "transactions.csv",
    output_dir: str = ".",
) -> bool:
    """Run the full data processing pipeline and return True only if all steps succeed."""
    processor = DataProcessor(customers_file)

    if not processor.load_data():
        logger.error("Failed to load customer data")
        return False

    if not processor.process_transactions(transactions_file):
        logger.error("Failed to process transactions")
        return False

    report_jobs = [
        ("customer_summary", os.path.join(output_dir, "customer_summary.json")),
        ("metrics", os.path.join(output_dir, "metrics.json")),
        ("transactions", os.path.join(output_dir, "transactions.json")),
    ]
    export_jobs = [
        (os.path.join(output_dir, "customers_export.csv"), "csv"),
        (os.path.join(output_dir, "customers_export.json"), "json"),
    ]

    failures: List[str] = []

    for report_type, out_path in report_jobs:
        if not processor.generate_report(report_type, out_path):
            failures.append(f"generate_report({report_type})")

    for out_path, fmt in export_jobs:
        if not processor.export_customer_data(out_path, fmt):
            failures.append(f"export_customer_data({fmt})")

    if failures:
        logger.error(f"Data processing completed with failures: {', '.join(failures)}")
        return False

    logger.info("Data processing completed successfully")
    return True


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process customer transaction data and generate analytics reports."
    )
    parser.add_argument(
        "--customers", default="customers.csv", help="Path to customers CSV file"
    )
    parser.add_argument(
        "--transactions",
        default="transactions.csv",
        help="Path to transactions CSV file",
    )
    parser.add_argument(
        "--output-dir", default=".", help="Directory for output reports and exports"
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    success = main(
        customers_file=args.customers,
        transactions_file=args.transactions,
        output_dir=args.output_dir,
    )
    sys.exit(0 if success else 1)
