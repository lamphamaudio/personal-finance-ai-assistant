"""LLM-based transaction categoriser supporting Gemini and OpenAI."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from spectra.categories import OTHER, normalize_category, normalize_recurring

logger = logging.getLogger("spectra.ai")


class CategorySuggestion(BaseModel):
    """Candidate category returned by the local classifier for review."""

    category: str
    score: float


class CategorisedTransaction(BaseModel):
    """A transaction after AI/local processing."""

    original_description: str
    clean_name: str
    category: str
    amount: float
    currency: str
    original_amount: float | None = None
    original_currency: str | None = None
    date: str
    id: str
    statement_category: str = ""
    recurring: str = ""
    classification_source: str = ""
    category_confidence: float | None = None
    category_suggestions: list[CategorySuggestion] = Field(default_factory=list)
    needs_review: bool = False


_SYSTEM_PROMPT = """\
Bạn là trợ lý tài chính cá nhân cho người dùng Việt Nam. Hãy phân tích giao dịch ngân hàng và trả về JSON array hợp lệ.

QUY TẮC PHÂN LOẠI:
1. Làm sạch mô tả giao dịch thành tên merchant dễ đọc, nhưng không dịch tên merchant.
2. Luôn tái sử dụng category hiện có nếu phù hợp. Không tạo category quá chi tiết.
3. Chỉ dùng category rộng bằng tiếng Việt:
   "Thu nhập", "Lương", "Ăn uống", "Đi chợ/Siêu thị", "Di chuyển", "Mua sắm",
   "Nhà ở", "Điện nước", "Sức khỏe", "Giải trí", "Du lịch", "Đăng ký định kỳ",
   "Chuyển khoản", "Bảo hiểm", "Giáo dục", "Tiền mặt", "Hoàn tiền", "Đầu tư",
   "Khác", "Chưa phân loại".
4. Apple, Spotify, Netflix, YouTube Premium, cloud, domain, SaaS dùng "Đăng ký định kỳ".
5. Nếu amount > 0, dùng category thu nhập như "Lương", "Thu nhập", "Hoàn tiền", "Đầu tư" hoặc "Chuyển khoản".
6. Field "recurring":
   - "Đăng ký định kỳ" cho khoản chi lặp lại như Netflix, Spotify, điện thoại, gym, bảo hiểm, SaaS.
   - "Thu nhập định kỳ" cho lương hoặc thu nhập đều kỳ.
   - "" cho giao dịch một lần.
7. Chỉ trả về JSON array, không thêm giải thích.

OUTPUT FORMAT:
[
  {
    "original": "<raw description>",
    "clean_name": "<merchant name>",
    "category": "<category tiếng Việt>",
    "amount": <amount as number>,
    "currency": "<currency code>",
    "date": "<YYYY-MM-DD>",
    "recurring": "<Đăng ký định kỳ|Thu nhập định kỳ|>"
  }
]
"""


def _build_user_prompt(
    transactions: list[dict[str, Any]],
    existing_categories: list[str],
) -> str:
    cats_str = (
        ", ".join(f'"{normalize_category(c)}"' for c in existing_categories)
        if existing_categories
        else "(chưa có)"
    )

    lines = [
        f"CATEGORY HIỆN CÓ: [{cats_str}]",
        "",
        "GIAO DỊCH CẦN PHÂN LOẠI:",
    ]
    for t in transactions:
        counterpart = str(t.get("counterpart", "")).strip()
        counterpart_part = f', đối tác: "{counterpart}"' if counterpart else ""
        lines.append(
            f'- mô tả: "{t["raw_description"]}", '
            f'số tiền: {t["amount"]}, tiền tệ: {t["currency"]}, ngày: {t["date"]}{counterpart_part}'
        )

    return "\n".join(lines)


def _call_gemini(user_prompt: str, api_key: str, model: str) -> str:
    import google.generativeai as genai  # type: ignore[import-untyped]

    genai.configure(api_key=api_key)
    llm = genai.GenerativeModel(model_name=model, system_instruction=_SYSTEM_PROMPT)
    response = llm.generate_content(user_prompt)
    return response.text


def _call_openai(user_prompt: str, api_key: str, model: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or "[]"


def _extract_json(text: str) -> list[dict[str, Any]]:
    """Robustly extract a JSON array from LLM output."""
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for value in parsed.values():
                if isinstance(value, list):
                    return value
            return [parsed]
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.error("Failed to parse LLM response as JSON: %s", text[:300])
    return []


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def categorise(
    transactions: list[dict[str, Any]],
    existing_categories: list[str],
    *,
    provider: str,
    api_key: str,
    model: str,
    base_currency: str = "VND",
) -> list[CategorisedTransaction]:
    """Send transactions to the selected AI provider and return structured results."""
    if not transactions:
        logger.info("No transactions to categorise")
        return []

    user_prompt = _build_user_prompt(transactions, existing_categories)
    logger.info("Sending %d transaction(s) to %s (%s)", len(transactions), provider, model)
    logger.debug("Prompt:\n%s", user_prompt)

    if provider == "gemini":
        raw = _call_gemini(user_prompt, api_key, model)
    elif provider == "openai":
        raw = _call_openai(user_prompt, api_key, model)
    else:
        raise ValueError(f"Unknown AI provider: {provider!r}")

    logger.debug("Raw LLM response:\n%s", raw)
    items = _extract_json(raw)
    logger.info("LLM returned %d categorised item(s)", len(items))

    import hashlib

    results: list[CategorisedTransaction] = []
    for item in items:
        try:
            amount = float(item.get("amount", 0))
            date_str = str(item.get("date", ""))
            desc_str = str(item.get("original", ""))
            raw_id = f"{date_str}:{desc_str}:{amount}"
            txn_id = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()

            results.append(
                CategorisedTransaction(
                    id=txn_id,
                    original_description=desc_str,
                    clean_name=str(item.get("clean_name", "")),
                    category=normalize_category(str(item.get("category", OTHER))),
                    amount=amount,
                    currency=str(item.get("currency", base_currency)),
                    date=date_str,
                    statement_category=str(item.get("statement_category", "") or ""),
                    recurring=normalize_recurring(str(item.get("recurring", "")), amount),
                    original_amount=None,
                    original_currency=None,
                )
            )
        except Exception:
            logger.warning("Skipping malformed LLM item: %s", item)

    return results


def _normalize_recurring(value: Any, amount: float) -> str:
    """Backward-compatible helper for tests/importers."""
    if isinstance(value, bool):
        value = "true" if value else ""
    return normalize_recurring(str(value or ""), amount)
