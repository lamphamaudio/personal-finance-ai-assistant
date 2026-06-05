"""Utilities for running chatbot regression checks from the docs dataset."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from spectra.chat.models import ChatIntent
from spectra.chat.tools import get_registered_tools


@dataclass(frozen=True)
class EvaluationCase:
    group: str
    question: str
    expected_intent: str
    expected_tool: str
    requires_confirmation: bool
    pass_criteria: str


def _table_rows(lines: Iterable[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 6 or cells[0] in {"Group", "---"}:
            continue
        rows.append(cells)
    return rows


def load_evaluation_cases(path: str | Path = "docs/chatbot-evaluation.md") -> list[EvaluationCase]:
    doc = Path(path)
    rows = _table_rows(doc.read_text(encoding="utf-8").splitlines())
    return [
        EvaluationCase(
            group=group,
            question=question,
            expected_intent=expected_intent,
            expected_tool=expected_tool,
            requires_confirmation=confirmation.lower() == "yes",
            pass_criteria=pass_criteria,
        )
        for group, question, expected_intent, expected_tool, confirmation, pass_criteria in rows
    ]


def validate_contract(cases: Iterable[EvaluationCase]) -> list[str]:
    tools = get_registered_tools()
    intents = {intent.value for intent in ChatIntent}
    errors: list[str] = []
    for case in cases:
        if case.expected_intent not in intents:
            errors.append(f"{case.group}: unknown intent {case.expected_intent!r}")
        if case.expected_tool != "None" and case.expected_tool not in tools:
            errors.append(f"{case.group}: unknown tool {case.expected_tool!r}")
    return errors


def _post_chat(base_url: str, cookie: str, question: str) -> dict[str, object]:
    body = json.dumps({"message": question}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=body,
        headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def run_api_evaluation(cases: Iterable[EvaluationCase], *, base_url: str, cookie: str = "") -> list[str]:
    failures: list[str] = []
    for case in cases:
        try:
            payload = _post_chat(base_url, cookie, case.question)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            failures.append(f"{case.group}: API call failed for {case.question!r}: {exc}")
            continue

        actual_intent = str(payload.get("intent") or "")
        tool_calls = payload.get("tool_calls") if isinstance(payload.get("tool_calls"), list) else []
        actual_tool = str((tool_calls[0] or {}).get("tool_name") or "None") if tool_calls else "None"
        actual_confirmation = bool(payload.get("requires_confirmation"))

        if actual_intent != case.expected_intent:
            failures.append(f"{case.group}: expected intent {case.expected_intent}, got {actual_intent}")
        if actual_tool != case.expected_tool:
            failures.append(f"{case.group}: expected tool {case.expected_tool}, got {actual_tool}")
        if actual_confirmation != case.requires_confirmation:
            failures.append(
                f"{case.group}: expected confirmation {case.requires_confirmation}, got {actual_confirmation}"
            )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run chatbot evaluation checks from docs/chatbot-evaluation.md")
    parser.add_argument("--docs", default="docs/chatbot-evaluation.md", help="Path to the evaluation markdown file")
    parser.add_argument("--base-url", default="", help="Optional live Spectra API URL, for example http://localhost:8001")
    parser.add_argument("--cookie", default="", help="Optional raw Cookie header for authenticated API runs")
    args = parser.parse_args(argv)

    cases = load_evaluation_cases(args.docs)
    errors = validate_contract(cases)
    if args.base_url:
        errors.extend(run_api_evaluation(cases, base_url=args.base_url, cookie=args.cookie))

    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1

    mode = "contract + API" if args.base_url else "contract"
    print(f"PASS {mode}: {len(cases)} evaluation case(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
