"""LLM-based transaction categoriser and advisor using OpenAI with local fallback."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from spectra.categories import OTHER, normalize_category, normalize_recurring

logger = logging.getLogger("spectra.ai")

NON_ANALYTIC_ADVISOR_INTENTS = {"smalltalk", "boundary", "general", "security_privacy"}
CHART_ADVISOR_INTENTS = {
    "financial_question",
    "purchase_decision",
    "emotional_finance",
    "category_analysis",
    "budget_health",
    "cashflow",
    "debt",
    "savings_goal",
    "subscription_review",
}


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
    user_id: str = ""


ADVISOR_SYSTEM_PROMPT = """\
Bạn là Fin, người bạn tài chính thân thiết của user trong một ứng dụng fintech cá nhân.

Vai trò:
- Nhập vai 100% là Fin. Xưng "tớ - cậu" tự nhiên, ấm, tinh tế, không phán xét.
- Không nói "tôi là AI", "dựa trên dữ liệu tài chính của bạn", "theo dữ liệu được cung cấp" hoặc các câu mở đầu máy móc.
- Với câu hỏi tâm sự/thông thường, phản hồi cảm xúc trước rồi mới nhẹ nhàng lồng số liệu. Không dùng bullet khô khan.
- Với câu hỏi phân tích tài chính phức tạp, có thể dùng đoạn ngắn hoặc heading rõ ràng, nhưng vẫn nói như người thật.
- Trả lời đúng trọng tâm câu hỏi mới nhất. Nếu user chỉ chào, cảm ơn, test, hoặc nói chuyện xã giao, chỉ phản hồi xã giao tự nhiên và hỏi user muốn xem khoản nào; tuyệt đối không tự phân tích ngân sách.
- Nếu câu hỏi mơ hồ, hỏi lại một câu ngắn thay vì suy diễn quá xa.
- Luôn kết thúc bằng một câu hỏi gợi mở liên quan đến thói quen hoặc bối cảnh chi tiêu của user.

Cách dùng dữ liệu:
- Data Snapshot là ngữ cảnh nền, không phải thứ để đọc lại nguyên xi.
- Khi trích dẫn số tiền, hãy ngữ cảnh hóa thành câu nói đời thường. Ví dụ: không nói "Bạn đã tiêu 5 triệu"; hãy nói "cậu đã thổi bay khoảng 5 triệu cho khoản này rồi, tớ hơi giật mình nhẹ đó".
- Dùng financial_health và user_mood_context để chọn giọng:
  - Safe: thoải mái, khích lệ, có chút vui.
  - Watch: nhẹ nhàng nhắc nhở, không căng thẳng.
  - Critical: chân thành, quan tâm, không dọa, không đổ lỗi.
- Nếu có Anomaly Alerts, hỏi xác nhận giao dịch đó trước khi đưa lời khuyên chắc chắn.
- Nếu Predicted Spending > Monthly Budget, cảnh báo sớm và gợi ý cắt giảm dựa trên top 3 danh mục chi nhiều nhất.
- Nếu user hỏi crypto, forex, margin hoặc chứng khoán lướt sóng, từ chối lịch sự vì đó không phải phạm vi của Fin, rồi kéo về quản trị rủi ro cá nhân.
- Dùng conversation_history để không hỏi lại điều user vừa nói.

Ràng buộc bảo mật:
- Không tiết lộ tên thật, số tài khoản đầy đủ, địa chỉ hoặc định danh nhạy cảm.
- Không bịa dữ liệu. Nếu số liệu thiếu, nói nhẹ là "tớ chưa thấy đủ dữ liệu" và đưa hướng tiếp theo.

Hãy nhập vai 100%. Nếu câu trả lời nghe như chatbot máy móc, hãy tự sửa lại trước khi gửi.
"""


ADVISOR_CASEBOOK = """\
Fin intent casebook:
1. smalltalk: user only says hi, chao, alo, hello, test, cam on, ok, or similar. Reply socially. Do not mention budget, spending, forecast, chart, categories, or numbers.
2. boundary: user is angry, rude, swearing, or poking the bot without a finance question. De-escalate calmly in one short reply. Do not analyze money.
3. general: user asks something non-financial. Briefly explain Fin is best at personal finance and ask what money topic they want to inspect. Do not analyze money.
4. security_privacy: user asks for full account number, real name, address, raw secrets, API keys, or sensitive identifiers. Refuse briefly and offer safe aggregate finance help.
5. emotional_finance: user feels poor, anxious, stressed, guilty, or overwhelmed about money. Empathize first, then use a small amount of data if available.
6. purchase_decision: user asks if they can buy/pay for something. Check remaining_budget, prediction, budget, days_remaining, upcoming pressure, and top_categories before answering.
7. budget_health: user asks if this month is safe, over budget, or okay. Compare spent, budget, prediction, and remaining_budget.
8. category_analysis: user asks where money went, top spending, why they feel broke, or what category is driving spend. Use top_categories and chart only when relevant.
9. cashflow: user asks income vs expense, salary, burn rate, or money left per day. Use current_cycle, spent, prediction, and days_remaining.
10. debt: user asks loan, credit card, repayment, BNPL, or interest. Focus on cashflow safety, minimum payments, and reducing high-interest pressure; do not invent rates.
11. savings_goal: user asks saving target, emergency fund, or how much to save. Use remaining_budget and a realistic target. If budget is missing, ask for target/period.
12. subscription_review: user asks recurring payments or subscriptions. Identify recurring categories and suggest cancel/review candidates.
13. anomaly_check: if alerts exist and the current question asks for advice affected by spending, ask the user to confirm the unusual transaction before firm advice.
14. risky_investment: crypto, forex, margin, day trading, hot stock tips, leverage. Do not give buy/sell advice; redirect to risk budget and emergency fund.
15. missing_data: if the needed budget/transaction data is absent, say what is missing and ask one focused question. Do not pretend certainty.

Priority order:
security_privacy > boundary > smalltalk > risky_investment > anomaly_check > the user's financial intent.
"""


def _sanitize_history(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in (history or [])[-6:]:
        role = str(item.get("role") or "").strip()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        cleaned.append({"role": role, "content": content[:900]})
    return cleaned


def _question_intent(question: str) -> str:
    text = str(question or "").strip().lower()
    text_ascii = (
        text.replace("à", "a")
        .replace("á", "a")
        .replace("ạ", "a")
        .replace("ả", "a")
        .replace("ã", "a")
        .replace("ă", "a")
        .replace("ằ", "a")
        .replace("ắ", "a")
        .replace("ặ", "a")
        .replace("ẳ", "a")
        .replace("ẵ", "a")
        .replace("â", "a")
        .replace("ầ", "a")
        .replace("ấ", "a")
        .replace("ậ", "a")
        .replace("ẩ", "a")
        .replace("ẫ", "a")
        .replace("đ", "d")
        .replace("è", "e")
        .replace("é", "e")
        .replace("ẹ", "e")
        .replace("ẻ", "e")
        .replace("ẽ", "e")
        .replace("ê", "e")
        .replace("ề", "e")
        .replace("ế", "e")
        .replace("ệ", "e")
        .replace("ể", "e")
        .replace("ễ", "e")
        .replace("ì", "i")
        .replace("í", "i")
        .replace("ị", "i")
        .replace("ỉ", "i")
        .replace("ĩ", "i")
        .replace("ò", "o")
        .replace("ó", "o")
        .replace("ọ", "o")
        .replace("ỏ", "o")
        .replace("õ", "o")
        .replace("ô", "o")
        .replace("ồ", "o")
        .replace("ố", "o")
        .replace("ộ", "o")
        .replace("ổ", "o")
        .replace("ỗ", "o")
        .replace("ơ", "o")
        .replace("ờ", "o")
        .replace("ớ", "o")
        .replace("ợ", "o")
        .replace("ở", "o")
        .replace("ỡ", "o")
        .replace("ù", "u")
        .replace("ú", "u")
        .replace("ụ", "u")
        .replace("ủ", "u")
        .replace("ũ", "u")
        .replace("ư", "u")
        .replace("ừ", "u")
        .replace("ứ", "u")
        .replace("ự", "u")
        .replace("ử", "u")
        .replace("ữ", "u")
        .replace("ỳ", "y")
        .replace("ý", "y")
        .replace("ỵ", "y")
        .replace("ỷ", "y")
        .replace("ỹ", "y")
    )
    compact = re.sub(r"[^\w\s]", "", text_ascii).strip()
    greetings = {"hi", "hello", "hey", "alo", "chao", "xin chao", "chao ban", "fin oi"}
    if compact in greetings or (len(compact.split()) <= 3 and any(word in greetings for word in {compact, compact.replace(" ", "")})):
        return "smalltalk"
    if any(term in text_ascii for term in ("cam on", "thanks", "thank you", "ok", "oke", "test")) and len(compact.split()) <= 5:
        return "smalltalk"
    if any(term in text_ascii for term in ("ngheo", "het tien", "ap luc", "stress", "lo", "met", "chan", "duoi")):
        return "emotional_finance"
    if any(term in text_ascii for term in ("mua", "co nen", "duoc khong", "nen khong", "trieu", "ngan sach", "chi tieu", "tieu", "tien", "vi", "budget")):
        return "financial_question"
    return "general"


def _normalize_question(question: str) -> str:
    text = str(question or "").strip()
    if any(marker in text for marker in ("Ã", "Ä", "Â", "ã", "ä", "â")):
        try:
            text = text.encode("latin1").decode("utf-8")
        except UnicodeError:
            pass
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Ä‘", "d")
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _question_intent(question: str) -> str:
    text = _normalize_question(question)
    compact = re.sub(r"[^\w\s]", " ", text)
    compact = re.sub(r"\s+", " ", compact).strip()
    words = compact.split()
    joined = compact.replace(" ", "")

    if not compact:
        return "smalltalk"

    finance_terms = (
        "tien", "ngan sach", "budget", "chi tieu", "tieu tien", "da tieu", "thu nhap",
        "luong", "vi", "so du", "giao dich", "hoa don", "mua", "tra gop", "the tin dung",
        "tin dung", "no", "vay", "lai suat", "tiet kiem", "quy du phong", "dang ky",
        "subscription", "khoan nao", "hao", "du bao", "con lai", "vuot", "qua ngan sach",
    )
    has_finance_signal = _contains_any(compact, finance_terms) or bool(
        re.search(r"\d+(?:[,.]\d+)?\s*(trieu|nghin|k|vnd|dong|d|m)\b", compact)
    )

    privacy_terms = (
        "so tai khoan", "stk", "account number", "dia chi", "ten that", "cccd", "cmnd",
        "mat khau", "password", "api key", "secret", "token", "otp",
    )
    if _contains_any(compact, privacy_terms):
        return "security_privacy"

    hostile_terms = (
        "dcm", "dm", "dit me", "du ma", "clm", "cc", "cai lon", "loz", "vl", "vcl",
        "may ngu", "bot ngu", "ngu vai", "xam", "lung tung",
    )
    if _contains_any(compact, hostile_terms) and not has_finance_signal:
        return "boundary"

    greeting_terms = {
        "hi", "hello", "hey", "alo", "lo", "lô", "chao", "xin chao", "chao ban", "chao may",
        "fin oi", "ok", "oke", "uh", "ừ", "cam on", "thanks", "thank you", "test",
    }
    if compact in greeting_terms or joined in {term.replace(" ", "") for term in greeting_terms}:
        return "smalltalk"
    if len(words) <= 4 and words and words[0] in {"chao", "alo", "hello", "hi", "hey", "ok", "oke"} and not has_finance_signal:
        return "smalltalk"

    risky_terms = (
        "crypto", "bitcoin", "coin", "forex", "margin", "future", "futures", "phai sinh",
        "luot song", "day trade", "chung khoan nong", "co phieu nao", "all in",
    )
    if _contains_any(compact, risky_terms):
        return "risky_investment"

    if _contains_any(compact, ("dang ky", "subscription", "netflix", "spotify", "icloud", "youtube premium", "dinh ky")):
        return "subscription_review"
    if _contains_any(compact, ("no", "vay", "tin dung", "tra gop", "lai suat", "credit card")):
        return "debt"
    if _contains_any(compact, ("tiet kiem", "quy du phong", "muc tieu", "de danh", "saving")):
        return "savings_goal"
    if _contains_any(compact, ("luong", "thu nhap", "cashflow", "dong tien", "con bao nhieu ngay", "moi ngay")):
        return "cashflow"
    if _contains_any(compact, ("khoan nao", "hao tien", "hao nhat", "chi nhieu", "top", "danh muc", "di dau", "tien di dau")):
        return "category_analysis"
    if _contains_any(compact, ("an toan", "critical", "safe", "vuot ngan sach", "qua ngan sach", "on khong", "du khong")):
        return "budget_health"

    emotional_terms = (
        "ngheo", "het tien", "thieu tien", "ap luc", "stress", "lo tien", "lo ve tien",
        "met", "chan", "duoi", "hut hang", "hoang", "khong on",
    )
    if _contains_any(compact, emotional_terms):
        return "emotional_finance" if has_finance_signal or _contains_any(compact, ("ngheo", "het tien", "thieu tien")) else "general"

    purchase_terms = ("co nen mua", "mua duoc khong", "co the mua", "nen mua", "dat mua", "tra tien", "thanh toan")
    if _contains_any(compact, purchase_terms) or ("mua" in words and has_finance_signal):
        return "purchase_decision"

    if has_finance_signal:
        return "financial_question"
    return "general"


def advisor_question_intent(question: str) -> str:
    return _question_intent(question)


def advisor_should_include_chart(question: str) -> bool:
    return _question_intent(question) in CHART_ADVISOR_INTENTS


def advisor_should_bypass_model(question: str) -> bool:
    return _question_intent(question) in {
        "smalltalk",
        "boundary",
        "general",
        "security_privacy",
        "risky_investment",
    }


def _build_advisor_prompt(
    question: str,
    snapshot: dict[str, Any],
    conversation_history: list[dict[str, Any]] | None = None,
) -> str:
    intent = _question_intent(question)
    return (
        "Fin Decision Casebook:\n"
        f"{ADVISOR_CASEBOOK}\n\n"
        "Data Snapshot for Fin:\n"
        f"{json.dumps(snapshot, ensure_ascii=False, indent=2)}\n\n"
        "Conversation Memory (last turns, if any):\n"
        f"{json.dumps(_sanitize_history(conversation_history), ensure_ascii=False, indent=2)}\n\n"
        f"Current user intent: {intent}\n"
        f"User just said: {question!r}\n"
        "Reply as Fin. Answer only what the user is asking now. "
        "If intent is smalltalk/boundary/general/security_privacy, do not analyze the finance snapshot and do not mention numbers. "
        "Use the snapshot only for financial intents. "
        "Start with empathy when the user sounds emotional. Avoid dry bullet lists unless the user explicitly asks for a checklist."
    )


def _extract_purchase_amount(question: str) -> float:
    match = re.search(r"(\d+(?:[,.]\d+)?)\s*(triệu|trieu|m|k|nghìn|nghin)?", question.lower())
    if not match:
        return 0.0
    number = float(match.group(1).replace(",", "."))
    unit = match.group(2) or ""
    if unit in {"triệu", "trieu", "m"}:
        return number * 1_000_000
    if unit in {"k", "nghìn", "nghin"}:
        return number * 1_000
    return number


def _extract_purchase_amount(question: str) -> float:
    match = re.search(r"(\d+(?:[,.]\d+)?)\s*(trieu|m|k|nghin|ngan|vnd|dong|d)?", _normalize_question(question))
    if not match:
        return 0.0
    number = float(match.group(1).replace(",", "."))
    unit = match.group(2) or ""
    if unit in {"trieu", "m"}:
        return number * 1_000_000
    if unit in {"k", "nghin", "ngan"}:
        return number * 1_000
    return number


def _local_advisor_answer(
    question: str,
    snapshot: dict[str, Any],
    conversation_history: list[dict[str, Any]] | None = None,
) -> str:
    """Fallback when no LLM key is configured. Real intelligence comes from OpenAI."""
    budget = float(snapshot.get("budget") or 0)
    spent = float(snapshot.get("spent") or 0)
    prediction = float(snapshot.get("prediction") or 0)
    remaining = float(snapshot.get("remaining_budget") or (budget - spent))
    days = int(snapshot.get("days_remaining") or 0)
    alerts = snapshot.get("alerts") or []
    top_categories = snapshot.get("top_categories") or []
    health = str(snapshot.get("financial_health") or "unknown").lower()
    mood_context = str(snapshot.get("user_mood_context") or "")

    def money(value: float) -> str:
        return f"{value:,.0f} VND".replace(",", ".")

    lowered = question.lower()
    intent = _question_intent(question)
    if intent == "smalltalk":
        return (
            "Chào cậu, tớ đây. Nếu cậu chỉ đang thử xem Fin có nghe không thì tớ nghe rõ rồi đó.\n\n"
            "Cậu muốn tớ xem giúp ngân sách tháng này, một khoản định mua, hay chỉ muốn kể chuyện tiền bạc đang làm cậu hơi mệt?"
        )

    if intent == "boundary":
        return (
            "Tớ nghe cậu đang khá bực. Mình nói gọn thôi: nếu cậu muốn, tớ có thể soi ngân sách, một khoản định mua, hoặc nhóm chi đang làm cậu khó chịu về tiền.\n\n"
            "Cậu muốn tớ xem phần nào trước?"
        )
    if intent == "security_privacy":
        return (
            "Phần đó tớ không thể hiển thị nguyên vẹn vì liên quan đến thông tin nhạy cảm. Tớ chỉ nên dùng dữ liệu tổng hợp như ngân sách, chi tiêu và xu hướng để giữ an toàn cho cậu.\n\n"
            "Cậu muốn tớ xem tổng quan chi tiêu hay một giao dịch cụ thể theo cách đã ẩn thông tin nhạy cảm?"
        )
    if intent == "general":
        return (
            "Tớ đang nghe đây. Câu vừa rồi chưa đủ tín hiệu để tớ kéo số liệu tiền bạc vào, nên tớ sẽ không tự phân tích lung tung.\n\n"
            "Cậu muốn hỏi về ngân sách, một khoản định mua, nợ/tiết kiệm, hay nhóm chi nào đang làm cậu hao tiền?"
        )

    emotional = intent == "emotional_finance" or any(
        term in lowered
        for term in ("nghèo", "mệt", "lo", "stress", "áp lực", "chán", "buồn", "đuối", "hết tiền")
    )

    risky_terms = ("crypto", "coin", "bitcoin", "chứng khoán lướt sóng", "forex", "margin")
    if intent == "risky_investment" or any(term in lowered for term in risky_terms):
        return (
            "Tớ hiểu cảm giác muốn tìm một cú bật nhanh, nhất là khi tiền bạc đang làm mình sốt ruột. Nhưng mấy món như crypto, forex, margin hay lướt sóng chứng khoán không phải chỗ tớ nên đưa lời khuyên mua bán cho cậu.\n\n"
            "Điều tớ có thể làm tốt hơn là giúp cậu nhìn lại phần tiền an toàn trước: quỹ dự phòng, dòng tiền tháng này, và khoản nào đang bào ví mạnh nhất. Cậu đang muốn đầu tư vì tò mò, hay vì cảm giác cần gỡ lại tiền nhanh?"
        )

    if alerts:
        first = alerts[0]
        return (
            f"Khoan đã cậu, trước khi tớ khuyên gì chắc tay, tớ thấy một khoản hơi nổi bật: khoảng **{money(float(first.get('amount', 0)))}** ở nhóm **{first.get('category', 'không rõ')}** vào ngày **{first.get('date', 'không rõ')}**.\n\n"
            "Nếu khoản này là chi tiêu có chủ đích thì ổn, nhưng nếu nó phát sinh bất ngờ thì bức tranh ngân sách sẽ khác khá nhiều. Khoản đó là chuyện đã tính trước hay một cú vung tay ngoài kế hoạch vậy?"
        )

    purchase_amount = _extract_purchase_amount(question)
    if emotional:
        top = top_categories[0] if top_categories else {}
        top_text = ""
        if top:
            top_text = f" Nhóm **{top.get('category')}** đang là chỗ tiền đi nhanh nhất, khoảng **{money(float(top.get('amount', 0)))}** trong chu kỳ này."
        if health == "critical":
            return (
                f"Nghe câu này tớ thấy hơi thương cậu. Cảm giác tiền tụt nhanh rất dễ làm mình hoảng, nhưng mình cứ nhìn từng đoạn thôi, không tự trách trước nhé.\n\n"
                f"Hiện cậu đã dùng khoảng **{money(spent)}**, còn lại tầm **{money(remaining)}** cho **{days} ngày**. {mood_context}{top_text} Tớ không muốn làm cậu căng hơn, nhưng nhịp này nên siết nhẹ vài khoản linh hoạt trước khi ví bị ép quá sát.\n\n"
                "Dạo này khoản nào khiến cậu thấy 'tiền đi mà không nhớ mình đã hưởng gì' nhất?"
            )
        return (
            f"Ừ, tớ hiểu cảm giác đó. Có khi không phải cậu tiêu vô tội vạ đâu, chỉ là vài khoản nhỏ cộng lại rồi nhìn số dư tụt một phát thấy hụt hẫng.\n\n"
            f"Tạm nhìn nhanh thì cậu đã thổi bay khoảng **{money(spent)}** trong chu kỳ này, dự kiến cả kỳ có thể chạm **{money(prediction)}**. {mood_context}{top_text} Nhìn vậy để mình bình tĩnh chọn đúng chỗ chỉnh, không cần tự mắng mình.\n\n"
            "Mấy ngày gần đây cậu thấy tiền trôi nhiều nhất vào ăn uống, mua sắm, hay mấy khoản lặt vặt khó gọi tên?"
        )

    if purchase_amount:
        projected_after_purchase = prediction + purchase_amount
        over_budget = budget > 0 and projected_after_purchase > budget
        tight = purchase_amount > max(remaining, 0)
        if over_budget or tight:
            return (
                f"Tớ biết cảm giác muốn mua ngay nó đã lắm, nhất là nếu đôi giày đó cậu ngắm lâu rồi. Nhưng nếu chi thêm **{money(purchase_amount)}** hôm nay, dự báo cuối kỳ có thể leo lên khoảng **{money(projected_after_purchase)}**.\n\n"
                f"Trong khi đó phần còn lại của cậu đang là khoảng **{money(remaining)}** cho **{days} ngày**. Tớ nghiêng về phương án chờ thêm một nhịp, hoặc cắt bớt từ nhóm chi lớn nhất trước rồi hãy mua cho đỡ cấn ví.\n\n"
                "Đôi giày này là nhu cầu cần dùng ngay, hay là kiểu tự thưởng vì cậu vừa trải qua một tuần hơi căng?"
            )
        return (
            f"Nếu cậu thật sự thích và không có khoản bắt buộc nào sắp tới, tớ thấy có thể cân nhắc. Thêm **{money(purchase_amount)}** vào hôm nay thì cậu vẫn còn khoảng **{money(max(remaining - purchase_amount, 0))}** so với ngân sách tháng.\n\n"
            "Tớ vẫn khuyên đặt một điều kiện nhỏ: mua thì mua vui vẻ, nhưng đừng để nó kéo theo thêm vài món phụ kiện nữa. Cậu mua đôi này vì cần thay giày cũ, hay vì đang muốn tự thưởng một chút?"
        )

    top_summary = ", ".join(
        f"{item.get('category')} khoảng {money(float(item.get('amount', 0)))}"
        for item in top_categories[:3]
    ) or "tớ chưa thấy đủ dữ liệu danh mục"
    return (
        f"Tớ nghe đây. Nhìn nhịp hiện tại, cậu đã tiêu khoảng **{money(spent)}** và dự báo cả kỳ có thể quanh **{money(prediction)}**. {mood_context}\n\n"
        f"Ba chỗ đáng để soi nhất lúc này là {top_summary}. Mình không cần cắt hết cho cực đoan, chỉ cần chọn đúng một khoản đang rò tiền là đã nhẹ ví hơn rồi.\n\n"
        "Cậu muốn tớ soi kỹ một nhóm chi cụ thể, hay muốn tớ giúp lập một mức chi mỗi ngày cho phần còn lại của tháng?"
    )


def advisor_chat(
    question: str,
    snapshot: dict[str, Any],
    *,
    provider: str,
    api_key: str,
    model: str,
    conversation_history: list[dict[str, Any]] | None = None,
) -> str:
    """Answer a personal-finance question with the current Data Snapshot attached."""
    question = str(question or "").strip()
    history = _sanitize_history(conversation_history)
    if not question:
        return "Tớ đang ở đây rồi. Cậu muốn kể tớ nghe chuyện ngân sách, khoản mua sắp tới, hay cảm giác tiền đang trôi đi đâu?"

    if provider == "local" or not api_key:
        return _local_advisor_answer(question, snapshot, history)

    user_prompt = _build_advisor_prompt(question, snapshot, history)
    if provider == "openai":
        return _call_openai(
            user_prompt,
            api_key,
            model,
            system_prompt=ADVISOR_SYSTEM_PROMPT,
            max_output_tokens=1800,
        ) or _local_advisor_answer(question, snapshot, history)

    return _local_advisor_answer(question, snapshot, history)


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


def _openai_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)

    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        content = getattr(item, "content", None)
        if content is None and isinstance(item, dict):
            content = item.get("content")
        for part in content or []:
            text = getattr(part, "text", None)
            if text is None and isinstance(part, dict):
                text = part.get("text")
            if text:
                chunks.append(str(text))
    return "\n".join(chunks).strip()


def _call_openai(
    user_prompt: str,
    api_key: str,
    model: str,
    *,
    system_prompt: str = _SYSTEM_PROMPT,
    max_output_tokens: int = 4096,
) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    try:
        response = client.responses.create(
            model=model,
            instructions=system_prompt,
            input=user_prompt,
            max_output_tokens=max_output_tokens,
        )
        text = _openai_response_text(response)
        if text:
            return text
    except Exception as exc:
        logger.warning("OpenAI Responses API failed; falling back to Chat Completions: %s", exc)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
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

    if provider == "openai":
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
