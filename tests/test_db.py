"""Unit tests for the Postgres bookmark database."""

from __future__ import annotations

import os

import pytest

from spectra.db import BookmarkDB


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL_TEST or DATABASE_URL is required for Postgres DB tests")
    return url


@pytest.fixture
def db(database_url: str):
    with BookmarkDB(database_url) as db:
        db.reset_all_data()
        yield db
        db.reset_all_data()


class TestSeenTransactions:
    """Transaction deduplication tests."""

    def test_unseen_returns_false(self, db: BookmarkDB) -> None:
        assert db.is_seen("tx-001") is False

    def test_mark_seen_then_is_seen(self, db: BookmarkDB) -> None:
        db.mark_seen("tx-001")
        assert db.is_seen("tx-001") is True

    def test_mark_seen_idempotent(self, db: BookmarkDB) -> None:
        db.mark_seen("tx-001")
        db.mark_seen("tx-001")
        assert db.is_seen("tx-001") is True

    def test_mark_seen_batch(self, db: BookmarkDB) -> None:
        db.mark_seen_batch(["tx-001", "tx-002", "tx-003"])
        assert db.is_seen("tx-001") is True
        assert db.is_seen("tx-002") is True
        assert db.is_seen("tx-003") is True
        assert db.is_seen("tx-999") is False

    def test_count(self, db: BookmarkDB) -> None:
        assert db.count() == 0
        db.mark_seen_batch(["a", "b", "c"])
        assert db.count() == 3


class TestOverrides:
    """LLM Feedback Loop override tests."""

    def test_save_and_get_overrides(self, db: BookmarkDB) -> None:
        overrides = {
            "AMZ AWS EMEA": {"clean_name": "AWS", "category": "Cloud Computing"},
            "UBER TRIP SAN FRAN": {"clean_name": "Uber", "category": "Di chuyển"},
        }

        db.save_overrides(overrides)
        fetched = db.get_overrides()

        assert len(fetched) == 2
        assert "AMZ AWS EMEA" in fetched
        assert fetched["AMZ AWS EMEA"]["clean_name"] == "AWS"
        assert fetched["UBER TRIP SAN FRAN"]["category"] == "Di chuyển"

    def test_save_overrides_upsert(self, db: BookmarkDB) -> None:
        db.save_overrides({"MCDONALDS STR": {"clean_name": "McDonalds", "category": "Food"}})
        assert db.get_overrides()["MCDONALDS STR"]["category"] == "Food"

        db.save_overrides({"MCDONALDS STR": {"clean_name": "McDonalds", "category": "Fast Food"}})
        fetched = db.get_overrides()

        assert len(fetched) == 1
        assert fetched["MCDONALDS STR"]["category"] == "Fast Food"


class TestContextManager:
    def test_context_manager(self, database_url: str) -> None:
        with BookmarkDB(database_url) as db:
            db.reset_all_data()
            db.mark_seen("tx-001")
            assert db.is_seen("tx-001") is True
            db.reset_all_data()


class TestResetDatabase:
    def test_reset_all_data_clears_tables(self, db: BookmarkDB) -> None:
        db.mark_seen_batch(["tx-1", "tx-2"])
        db.save_merchant_category("netflix", "Đăng ký định kỳ")
        db.save_overrides({
            "NETFLIX.COM": {"clean_name": "netflix", "category": "Đăng ký định kỳ"}
        })
        db.save_budget_limit("Đăng ký định kỳ", 100)

        deleted = db.reset_all_data()

        assert deleted["seen_transactions"] >= 2
        assert deleted["merchant_categories"] >= 1
        assert deleted["user_overrides"] >= 1
        assert deleted["budget_limits"] >= 1
        assert deleted["tx_history"] == 0

        assert db.count() == 0
        assert db.get_merchant_categories() == {}
        assert db.get_overrides() == {}
        assert db.get_budget_limits() == {}
