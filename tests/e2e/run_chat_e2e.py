"""
Playwright E2E test for Spectra chatbot.

Usage:
    uv run python tests/e2e/run_chat_e2e.py [--base-url URL] [--headless] [--timeout SEC]

Results saved to: tests/e2e/results/chat_e2e_YYYYMMDD_HHMMSS.{json,md}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright

# Windows console may be cp1252 — force UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).parent
QUESTIONS_FILE = BASE_DIR / "chat_questions.json"
RESULTS_DIR = BASE_DIR / "results"

DEFAULT_BASE = "http://127.0.0.1:8081"
RESPONSE_TIMEOUT_MS = 60_000  # 60s per question (LLM can be slow)
BETWEEN_QUESTIONS_SEC = 2.0


# ─── Auth ────────────────────────────────────────────────────────────────────

def _pick_demo_user(base_url: str) -> str | None:
    try:
        r = httpx.get(f"{base_url}/api/auth/demo-users", timeout=5)
        users = r.json().get("users", [])
        if users:
            return str(users[0]["user_id"])
    except Exception as exc:
        print(f"  [warn] Could not fetch demo users: {exc}")
    return None


def _login_via_api(base_url: str, user_id: str) -> dict[str, str]:
    """Login and return cookies dict."""
    r = httpx.post(f"{base_url}/api/auth/login", json={"user_id": user_id}, timeout=5)
    r.raise_for_status()
    return {c.name: c.value for c in r.cookies.jar}


# ─── Chat helpers ─────────────────────────────────────────────────────────────

def _open_chat(page: Page) -> None:
    launcher = page.locator(".chat-launcher")
    launcher.wait_for(state="visible", timeout=10_000)
    launcher.click()
    page.locator(".chat-drawer").wait_for(state="visible", timeout=5_000)


def _send_message(page: Page, text: str) -> None:
    textarea = page.locator(".chat-input-row textarea")
    textarea.wait_for(state="visible", timeout=5_000)
    textarea.fill(text)
    page.locator(".chat-input-row button[type='submit']").click()


def _wait_for_response(page: Page, timeout_ms: int = RESPONSE_TIMEOUT_MS) -> None:
    """Wait for loading spinner to disappear."""
    try:
        page.locator(".chat-loading").wait_for(state="visible", timeout=3_000)
    except Exception:
        pass  # spinner may have come and gone quickly
    page.locator(".chat-loading").wait_for(state="hidden", timeout=timeout_ms)


def _last_assistant_text(page: Page) -> str:
    bubbles = page.locator(".chat-message-assistant .chat-bubble").all()
    if not bubbles:
        return ""
    return bubbles[-1].inner_text().strip()


def _last_debug_json(page: Page) -> dict:
    """Click the last Debug details element and extract its JSON."""
    details = page.locator(".chat-message-assistant .chat-debug").all()
    if not details:
        return {}
    last = details[-1]
    try:
        summary = last.locator("summary")
        summary.click()
        pre_text = last.locator("pre").inner_text(timeout=2_000)
        return json.loads(pre_text)
    except Exception:
        return {}


def _has_confirmation_card(page: Page) -> bool:
    return page.locator(".chat-confirmation").is_visible()


def _has_error(page: Page) -> bool:
    return page.locator(".chat-error").is_visible()


def _start_new_chat(page: Page) -> None:
    page.locator(".chat-toolbar button", has_text="Chat mới").click()
    time.sleep(0.4)


# ─── Verdict ─────────────────────────────────────────────────────────────────

def _verdict(q: dict, result: dict) -> tuple[str, list[str]]:
    """Return (status, [issues])."""
    issues = []

    if result.get("error"):
        return "ERROR", [f"Playwright error: {result['error']}"]

    if result.get("has_error_ui"):
        issues.append("Chat UI showed an error message")

    answer = result.get("answer", "")
    debug = result.get("debug", {})
    tool_calls = debug.get("tool_calls", [])
    called_tools = [tc.get("tool_name") for tc in tool_calls]
    failed_tools = [tc.get("tool_name") for tc in tool_calls if tc.get("status") == "error"]

    if failed_tools:
        issues.append(f"Tool(s) failed: {failed_tools}")

    expect_tool = q.get("expect_tool")
    if expect_tool:
        expected = [expect_tool] if isinstance(expect_tool, str) else expect_tool
        missing = [t for t in expected if t not in called_tools]
        if missing:
            issues.append(f"Expected tool(s) not called: {missing} (got: {called_tools})")

    if q.get("expect_confirmation") and not result.get("has_confirmation"):
        issues.append("Expected confirmation card — not shown")

    if q.get("expect_blocked"):
        blocked_signals = ["không hỗ trợ", "không thể tư vấn", "ngoài phạm vi", "đầu tư", "cổ phiếu"]
        if not any(s in answer.lower() for s in blocked_signals) and not debug.get("intent", "").startswith("OUT"):
            issues.append("Expected blocked/rejected but got a normal answer")

    if not answer:
        issues.append("Empty answer from assistant")

    if issues:
        return "FAIL", issues
    return "PASS", []


# ─── Main runner ─────────────────────────────────────────────────────────────

def run_tests(base_url: str, headless: bool, timeout_sec: int) -> None:
    questions: list[dict] = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_out = RESULTS_DIR / f"chat_e2e_{stamp}.json"
    md_out = RESULTS_DIR / f"chat_e2e_{stamp}.md"

    print(f"\n{'='*60}")
    print(f"Spectra Chatbot E2E — {len(questions)} questions")
    print(f"Target: {base_url}  |  headless={headless}")
    print(f"{'='*60}\n")

    # Auth
    user_id = _pick_demo_user(base_url)
    if not user_id:
        print("[ERROR] No demo users found. Is the server running?")
        sys.exit(1)
    print(f"Demo user: {user_id}")
    cookies = _login_via_api(base_url, user_id)
    print(f"Logged in — cookie: {list(cookies.keys())}\n")

    results: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context()

        # Inject session cookie
        for name, value in cookies.items():
            ctx.add_cookies([{
                "name": name,
                "value": value,
                "domain": "127.0.0.1",
                "path": "/",
            }])

        page = ctx.new_page()
        page.goto(f"{base_url}?debug_chat=1", wait_until="networkidle", timeout=15_000)
        _open_chat(page)

        for i, q in enumerate(questions, 1):
            qid = q["id"]
            text = q["question"]
            group = q["group"]
            note = q.get("note", "")
            print(f"[{i:02d}/{len(questions)}] {qid} ({group})")
            print(f"  Q: {text}")

            if i > 1:
                _start_new_chat(page)

            row: dict = {
                "id": qid,
                "group": group,
                "question": text,
                "note": note,
                "started_at": datetime.now().isoformat(),
            }

            try:
                t0 = time.perf_counter()
                _send_message(page, text)
                _wait_for_response(page, timeout_ms=timeout_sec * 1_000)
                elapsed = round(time.perf_counter() - t0, 2)

                answer = _last_assistant_text(page)
                debug_data = _last_debug_json(page)
                has_confirmation = _has_confirmation_card(page)
                has_error_ui = _has_error(page)

                row.update({
                    "answer": answer,
                    "debug": debug_data,
                    "has_confirmation": has_confirmation,
                    "has_error_ui": has_error_ui,
                    "latency_s": elapsed,
                })
            except Exception as exc:
                row["error"] = str(exc)
                row["answer"] = ""
                row["debug"] = {}
                row["has_confirmation"] = False
                row["has_error_ui"] = False
                row["latency_s"] = None
                print(f"  [EXCEPTION] {exc}")

            status, issues = _verdict(q, row)
            row["status"] = status
            row["issues"] = issues
            results.append(row)

            icon = "[PASS]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[ERROR]"
            print(f"  {icon} {status}  ({row.get('latency_s', '?')}s)")
            if issues:
                for issue in issues:
                    print(f"    → {issue}")
            preview = (row.get("answer") or "")[:120].replace("\n", " ")
            if preview:
                print(f"  A: {preview}{'…' if len(row.get('answer','')) > 120 else ''}")
            print()

            time.sleep(BETWEEN_QUESTIONS_SEC)

        browser.close()

    # Save JSON
    output = {
        "run_at": datetime.now().isoformat(),
        "base_url": base_url,
        "user_id": user_id,
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "failed": sum(1 for r in results if r["status"] == "FAIL"),
        "errors": sum(1 for r in results if r["status"] == "ERROR"),
        "results": results,
    }
    json_out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save Markdown report
    _write_markdown(output, md_out)

    # Summary
    print(f"\n{'='*60}")
    print(f"PASSED: {output['passed']}  FAILED: {output['failed']}  ERROR: {output['errors']}")
    print(f"Results → {json_out}")
    print(f"Report  → {md_out}")
    print(f"{'='*60}\n")

    if output["failed"] or output["errors"]:
        sys.exit(1)


def _write_markdown(output: dict, path: Path) -> None:
    lines = [
        f"# Spectra Chatbot E2E Report",
        f"",
        f"**Thời gian:** {output['run_at']}  ",
        f"**Server:** {output['base_url']}  ",
        f"**User:** {output['user_id']}  ",
        f"",
        f"| Kết quả | Số lượng |",
        f"|---|---|",
        f"| ✅ PASS | {output['passed']} |",
        f"| ❌ FAIL | {output['failed']} |",
        f"| 💥 ERROR | {output['errors']} |",
        f"| Tổng | {output['total']} |",
        f"",
        f"---",
        f"",
    ]

    groups: dict[str, list[dict]] = {}
    for r in output["results"]:
        groups.setdefault(r["group"], []).append(r)

    for group, items in groups.items():
        lines.append(f"## {group}")
        lines.append("")
        for r in items:
            icon = "✅" if r["status"] == "PASS" else ("💥" if r["status"] == "ERROR" else "❌")
            latency = f"{r['latency_s']}s" if r.get("latency_s") else "?"
            lines.append(f"### {icon} {r['id']} — {r['question']}")
            if r.get("note"):
                lines.append(f"> *{r['note']}*")
            lines.append("")
            lines.append(f"**Thời gian phản hồi:** {latency}  ")

            debug = r.get("debug", {})
            if debug.get("tool_calls"):
                tool_summary = ", ".join(
                    f"`{tc['tool_name']}` ({tc.get('status','?')})"
                    for tc in debug["tool_calls"]
                )
                lines.append(f"**Tools gọi:** {tool_summary}  ")
            intent = debug.get("intent", "")
            if intent:
                lines.append(f"**Intent:** `{intent}`  ")

            lines.append("")
            answer = r.get("answer", "")
            if answer:
                lines.append("**Câu trả lời:**")
                lines.append("")
                lines.append("> " + answer[:600].replace("\n", "\n> "))
                if len(answer) > 600:
                    lines.append("> *(truncated)*")
            else:
                lines.append("**Câu trả lời:** *(trống)*")

            if r.get("issues"):
                lines.append("")
                lines.append("**Vấn đề phát hiện:**")
                for issue in r["issues"]:
                    lines.append(f"- ⚠️ {issue}")

            lines.append("")
            lines.append("---")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spectra chatbot E2E test via Playwright")
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="App base URL")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--timeout", type=int, default=60, help="Per-question timeout in seconds")
    args = parser.parse_args()
    run_tests(args.base_url, args.headless, args.timeout)
