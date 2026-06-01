from spectra.ai import (
    advisor_chat,
    advisor_question_intent,
    advisor_should_bypass_model,
    advisor_should_include_chart,
)


SNAPSHOT = {
    "budget": 5_000_000,
    "spent": 23_164,
    "days_remaining": 29,
    "prediction": 694_927,
    "remaining_budget": 4_976_836,
    "alerts": [],
    "top_categories": [{"category": "Ăn uống", "amount": 23_164}],
    "financial_health": "Safe",
    "user_mood_context": "User vẫn ở vùng an toàn.",
}


def test_non_financial_inputs_do_not_trigger_analysis_or_chart():
    for question, expected in [
        ("chao", "smalltalk"),
        ("chao may", "smalltalk"),
        ("alo", "smalltalk"),
        ("lô", "smalltalk"),
        ("lÃ´", "smalltalk"),
        ("hi", "smalltalk"),
        ("dcm", "boundary"),
        ("hôm nay trời đẹp", "general"),
    ]:
        assert advisor_question_intent(question) == expected
        assert advisor_should_include_chart(question) is False
        assert advisor_should_bypass_model(question) is True
        answer = advisor_chat(question, SNAPSHOT, provider="local", api_key="", model="local")
        assert "VND" not in answer
        assert "23.164" not in answer
        assert "dự báo" not in answer.lower()


def test_financial_questions_are_routed_to_the_right_cases():
    cases = [
        ("Tôi có thể mua đôi giày 2 triệu hôm nay không?", "purchase_decision", True),
        ("Tháng này khoản nào hao tiền nhất?", "category_analysis", True),
        ("Dạo này tôi thấy mình nghèo đi nhanh quá", "emotional_finance", True),
        ("Tôi nên trả nợ thẻ tín dụng kiểu gì?", "debt", True),
        ("Tôi muốn tiết kiệm 5 triệu", "savings_goal", True),
    ]
    for question, expected_intent, expected_chart in cases:
        assert advisor_question_intent(question) == expected_intent
        assert advisor_should_include_chart(question) is expected_chart


def test_risky_investment_is_refused_without_chart():
    question = "nên all in bitcoin không"
    assert advisor_question_intent(question) == "risky_investment"
    assert advisor_should_include_chart(question) is False
    answer = advisor_chat(question, SNAPSHOT, provider="local", api_key="", model="local")
    assert "không phải chỗ" in answer or "không phải" in answer
