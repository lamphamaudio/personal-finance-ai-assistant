from pathlib import Path

import os

import pytest

from spectra.categories import (
    GROCERIES,
    RECURRING_INCOME,
    RECURRING_SUBSCRIPTION,
    SALARY,
    SUBSCRIPTIONS,
    TRANSPORT,
    UNCATEGORIZED,
    normalize_category,
)
from spectra.csv_parser import _parse_amount, _parse_date, parse_csv
from spectra.db import BookmarkDB
from spectra.local_categorizer import categorise_local
from spectra.ml_classifier import train_classifier
from spectra.recurring import apply_recurring_tags


def test_vietnamese_csv_headers_debit_credit(tmp_path: Path):
    csv_path = tmp_path / "vcb.csv"
    csv_path.write_text(
        "Ngày giao dịch,Nội dung,Ghi nợ,Ghi có,Loại tiền\n"
        "28/05/2026,WINMART HOA DON,250.000,,VND\n"
        "28-05-2026,CONG TY ACME TRA LUONG,,35.000.000,VND\n",
        encoding="utf-8",
    )

    rows = parse_csv(str(csv_path), currency="VND")

    assert len(rows) == 2
    assert rows[0].date == "2026-05-28"
    assert rows[0].amount == -250000
    assert rows[1].amount == 35000000
    assert rows[0].currency == "VND"


def test_vietnamese_amount_and_date_formats():
    assert _parse_amount("1.234.567 VND") == 1234567
    assert _parse_amount("1,234,567") == 1234567
    assert _parse_amount("-250000") == -250000
    assert _parse_amount("250.000 VND") == 250000
    assert _parse_date("2026-05-28") == "2026-05-28"
    assert _parse_date("28/05/2026") == "2026-05-28"
    assert _parse_date("28-05-2026") == "2026-05-28"


def test_legacy_category_migration(tmp_path: Path):
    database_url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL_TEST or DATABASE_URL is required for Postgres DB tests")

    with BookmarkDB(database_url) as db:
        db.reset_all_data()
        db._conn.execute(
            """
            INSERT INTO app_tx_history (tx_id, date, clean_name, amount, category, original_description)
            VALUES ('t1', '2026-05-28', 'Netflix', -260000, 'Digital Subscriptions', 'NETFLIX')
            """
        )
        db._conn.execute(
            "INSERT INTO app_merchant_categories (clean_name, category) VALUES ('Grab', 'Transport')"
        )
        db._conn.execute(
            "INSERT INTO app_budget_limits (category, monthly_limit) VALUES ('Food & Dining', 1000000)"
        )
        db._conn.execute(
            "INSERT INTO app_category_rules (rule_type, pattern, category) VALUES ('contains', 'x', 'Custom Cat')"
        )
        db._conn.commit()

    with BookmarkDB(database_url) as db:
        tx_cat = db._conn.execute("SELECT category FROM app_tx_history WHERE tx_id = 't1'").fetchone()[0]
        merchant_cat = db._conn.execute("SELECT category FROM app_merchant_categories WHERE clean_name = 'Grab'").fetchone()[0]
        budget_cat = db._conn.execute("SELECT category FROM app_budget_limits").fetchone()[0]
        custom_cat = db._conn.execute("SELECT category FROM app_category_rules").fetchone()[0]
        db.reset_all_data()

    assert tx_cat == SUBSCRIPTIONS
    assert merchant_cat == TRANSPORT
    assert budget_cat == "Ăn uống"
    assert custom_cat == "Custom Cat"


def test_local_categorizer_returns_vietnamese_categories():
    clf = train_classifier([])
    rows = [
        {"raw_description": "NETFLIX.COM SUBSCRIPTION", "amount": -260000, "currency": "VND", "date": "2026-05-05"},
        {"raw_description": "GRAB BIKE DISTRICT 1", "amount": -72000, "currency": "VND", "date": "2026-05-04"},
        {"raw_description": "WINMART HOA DON", "amount": -684500, "currency": "VND", "date": "2026-05-02"},
    ]

    cats = {r.clean_name: normalize_category(r.category) for r in categorise_local(rows, {}, clf)}

    assert SUBSCRIPTIONS in cats.values()
    assert TRANSPORT in cats.values()
    assert GROCERIES in cats.values()


def test_recurring_labels_are_vietnamese():
    class Tx:
        def __init__(self, clean_name, description, amount, date):
            self.clean_name = clean_name
            self.original_description = description
            self.amount = amount
            self.date = date
            self.statement_category = ""
            self.recurring = ""

    txns = [
        Tx("Netflix", "NETFLIX.COM", -260000, "2026-05-05"),
        Tx("Acme", "THANH TOAN LUONG THANG 05", 35000000, "2026-05-01"),
    ]

    apply_recurring_tags(txns, {})

    assert txns[0].recurring == RECURRING_SUBSCRIPTION
    assert txns[1].recurring == RECURRING_INCOME
