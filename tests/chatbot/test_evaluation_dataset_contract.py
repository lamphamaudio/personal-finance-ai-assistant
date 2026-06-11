from spectra.chat.evaluation import load_evaluation_cases, validate_contract


def test_chatbot_evaluation_dataset_uses_known_intents_and_tools():
    cases = load_evaluation_cases()

    assert cases
    assert validate_contract(cases) == []
