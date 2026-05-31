"""Seed transactions for existing bank users that currently have no activity."""

from __future__ import annotations

import random

from data_seeder import (
    PERSONAS,
    TRANSACTIONS_PER_USER_MAX,
    TRANSACTIONS_PER_USER_MIN,
    calculate_transaction_patterns,
    generate_anomaly_reason,
    generate_transactions_for_user,
    get_db_connection,
    insert_transactions_batch,
)


def _force_some_anomalies(transactions: list[dict], minimum: int = 5) -> None:
    debit_rows = [tx for tx in transactions if tx["transaction_type"] == "debit"]
    current_anomalies = [tx for tx in debit_rows if tx["is_anomaly"]]
    needed = max(0, minimum - len(current_anomalies))
    if not needed:
        return

    candidates = [tx for tx in debit_rows if not tx["is_anomaly"]]
    for tx in random.sample(candidates, min(needed, len(candidates))):
        tx["is_anomaly"] = True
        tx["anomaly_reason"] = generate_anomaly_reason()
        tx["amount"] = float(tx["amount"]) * random.uniform(1.5, 2.0)


def find_empty_bank_users(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            ba.user_id,
            ba.id AS account_id,
            up.persona_type
        FROM bank_accounts ba
        JOIN user_personas up ON up.user_id = ba.user_id
        LEFT JOIN bank_transactions bt ON bt.user_id = ba.user_id
        GROUP BY ba.user_id, ba.id, up.persona_type
        HAVING COUNT(bt.id) = 0
        ORDER BY ba.created_at ASC, ba.user_id ASC
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    return rows


def clear_existing_patterns(conn, user_id) -> None:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transaction_patterns WHERE user_id = %s", (str(user_id),))
    conn.commit()
    cursor.close()


def seed_missing_transactions() -> None:
    conn = get_db_connection()
    try:
        empty_users = find_empty_bank_users(conn)
        if not empty_users:
            print("No empty bank users found.")
            return

        print(f"Found {len(empty_users)} bank user(s) without transactions.")
        for user_id, account_id, persona_type in empty_users:
            persona_config = PERSONAS[str(persona_type)]
            count = random.randint(TRANSACTIONS_PER_USER_MIN, TRANSACTIONS_PER_USER_MAX)
            transactions = generate_transactions_for_user(
                user_id,
                account_id,
                str(persona_type),
                persona_config,
                count,
            )
            _force_some_anomalies(transactions)
            insert_transactions_batch(conn, transactions)
            clear_existing_patterns(conn, user_id)
            calculate_transaction_patterns(conn, user_id)
            anomalies = sum(1 for tx in transactions if tx["is_anomaly"])
            print(f"Seeded {len(transactions)} transactions for {user_id} ({anomalies} anomalies).")
    finally:
        conn.close()


if __name__ == "__main__":
    seed_missing_transactions()
