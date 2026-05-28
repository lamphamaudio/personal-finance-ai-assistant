"""Vietnam-first canonical categories and compatibility helpers."""

from __future__ import annotations

UNCATEGORIZED = "Chưa phân loại"
SUBSCRIPTIONS = "Đăng ký định kỳ"
SALARY = "Lương"
INCOME = "Thu nhập"
FOOD = "Ăn uống"
GROCERIES = "Đi chợ/Siêu thị"
TRANSPORT = "Di chuyển"
SHOPPING = "Mua sắm"
HOUSING = "Nhà ở"
UTILITIES = "Điện nước"
HEALTH = "Sức khỏe"
ENTERTAINMENT = "Giải trí"
TRAVEL = "Du lịch"
TRANSFERS = "Chuyển khoản"
INSURANCE = "Bảo hiểm"
EDUCATION = "Giáo dục"
CASH = "Tiền mặt"
REFUND = "Hoàn tiền"
INVESTMENT = "Đầu tư"
OTHER = "Khác"

RECURRING_SUBSCRIPTION = "Đăng ký định kỳ"
RECURRING_INCOME = "Thu nhập định kỳ"

CATEGORIES = [
    INCOME,
    SALARY,
    FOOD,
    GROCERIES,
    TRANSPORT,
    SHOPPING,
    HOUSING,
    UTILITIES,
    HEALTH,
    ENTERTAINMENT,
    TRAVEL,
    SUBSCRIPTIONS,
    TRANSFERS,
    INSURANCE,
    EDUCATION,
    CASH,
    REFUND,
    INVESTMENT,
    OTHER,
    UNCATEGORIZED,
]

EN_TO_VI_CATEGORY = {
    "Uncategorized": UNCATEGORIZED,
    "Digital Subscriptions": SUBSCRIPTIONS,
    "Subscription": SUBSCRIPTIONS,
    "Subscriptions": SUBSCRIPTIONS,
    "Food & Dining": FOOD,
    "Food and Dining": FOOD,
    "Groceries": GROCERIES,
    "Transport": TRANSPORT,
    "Transportation": TRANSPORT,
    "Shopping": SHOPPING,
    "Housing": HOUSING,
    "Rent": HOUSING,
    "Utilities": UTILITIES,
    "Health": HEALTH,
    "Health & Fitness": HEALTH,
    "Fitness": HEALTH,
    "Entertainment": ENTERTAINMENT,
    "Travel": TRAVEL,
    "Transfers": TRANSFERS,
    "Transfer": TRANSFERS,
    "Transfer In": TRANSFERS,
    "Insurance": INSURANCE,
    "Education": EDUCATION,
    "Cash": CASH,
    "Cash Withdrawal": CASH,
    "Cash Deposit": CASH,
    "Refund": REFUND,
    "Reimbursement": REFUND,
    "Investment": INVESTMENT,
    "Investment Return": INVESTMENT,
    "Salary": SALARY,
    "Pension": INCOME,
    "Salary/Income": SALARY,
    "Other Income": INCOME,
    "Income": INCOME,
    "Taxes": OTHER,
    "Other": OTHER,
}


def normalize_category(value: str | None) -> str:
    """Return the Vietnamese canonical category for legacy or new labels."""
    raw = str(value or "").strip()
    if not raw:
        return UNCATEGORIZED
    if raw in CATEGORIES:
        return raw
    return EN_TO_VI_CATEGORY.get(raw, raw)


def is_uncategorized(value: str | None) -> bool:
    return normalize_category(value) == UNCATEGORIZED


def is_subscription_category(value: str | None) -> bool:
    return normalize_category(value) == SUBSCRIPTIONS


def normalize_recurring(value: str | None, amount: float = 0.0) -> str:
    """Normalize legacy recurring tags to Vietnamese labels."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered in {"false", "no", "none"}:
        return ""
    if lowered in {"true", "yes"}:
        return RECURRING_INCOME if amount > 0 else RECURRING_SUBSCRIPTION
    if raw in {RECURRING_SUBSCRIPTION, RECURRING_INCOME}:
        return raw
    if "subscription" in lowered or "đăng ký" in lowered:
        return RECURRING_SUBSCRIPTION
    if "salary" in lowered or "income" in lowered or "lương" in lowered or "thu nhập" in lowered:
        return RECURRING_INCOME
    return raw
