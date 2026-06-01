"""
Bank Simulator FastAPI Backend
===============================
REST API để các service khác lấy dữ liệu từ Bank Simulator

Endpoints:
- GET /transactions?user_id={uuid}
- GET /summary?user_id={uuid}
- GET /anomalies?user_id={uuid}
- GET /prediction?user_id={uuid}
- GET /users (List all users)
- GET /stats (Overall statistics)
"""

import base64
import hashlib
import hmac
import html as html_lib
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

import psycopg
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables from local .env file
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# ============================================================================
# Configuration
# ============================================================================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in .env file")

API_PORT = int(os.getenv("BANK_SIMULATOR_PORT", "8000"))
API_HOST = os.getenv("BANK_SIMULATOR_HOST", "0.0.0.0")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
SSO_SHARED_SECRET = os.getenv("SSO_SHARED_SECRET", "change-me-for-local-demo")
SPECTRA_BASE_URL = os.getenv("SPECTRA_BASE_URL", "http://localhost:8081").rstrip("/")
BANK_SIMULATOR_BASE_URL = os.getenv("BANK_SIMULATOR_BASE_URL", "http://localhost:8000").rstrip("/")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "28800"))
SSO_TOKEN_TTL_SECONDS = int(os.getenv("SSO_TOKEN_TTL_SECONDS", "300"))
DEMO_BANK_PASSWORD = os.getenv("DEMO_BANK_PASSWORD", "Bank@123456")
PASSWORD_ITERATIONS = int(os.getenv("BANK_PASSWORD_ITERATIONS", "210000"))

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Bank Simulator API",
    description="REST API cho Financial AI Advisor - Bank Simulator Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Pydantic Models
# ============================================================================

class Transaction(BaseModel):
    id: str
    user_id: str
    account_id: str
    transaction_type: str
    amount: float
    merchant: str
    merchant_category: str
    category: str
    description: Optional[str] = None
    balance_after: float
    is_anomaly: bool
    anomaly_reason: Optional[str] = None
    location: Optional[str] = None
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    created_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v)
        }


class CategorySummary(BaseModel):
    category: str
    total_amount: float
    transaction_count: int
    avg_amount: float
    percentage: float


class SpendingSummary(BaseModel):
    user_id: str
    total_spending: float
    total_income: float
    net_cashflow: float
    categories: List[CategorySummary]
    period_days: int


class AnomalyTransaction(BaseModel):
    id: str
    amount: float
    merchant: str
    category: str
    anomaly_reason: str
    created_at: datetime
    severity: str  # low, medium, high


class PredictionResponse(BaseModel):
    user_id: str
    current_balance: float
    predicted_end_of_month_balance: float
    avg_daily_spending: float
    days_remaining: int
    spending_trend: str  # increasing, stable, decreasing
    recommendation: str


class UserInfo(BaseModel):
    user_id: str
    persona_type: str
    account_number: str
    bank_name: str
    current_balance: float
    transaction_count: int
    anomaly_count: int


class OverallStats(BaseModel):
    total_users: int
    total_transactions: int
    total_anomalies: int
    anomaly_rate: float
    total_volume: float
    personas: Dict[str, int]


# ============================================================================
# Database Helper Functions
# ============================================================================

def get_db_connection():
    """Tạo kết nối database"""
    return psycopg.connect(DATABASE_URL)


def row_to_dict(cursor, row) -> Dict[str, Any]:
    """Convert database row to dictionary"""
    if row is None:
        return {}
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


_AUTH_SCHEMA_READY = False


def ensure_auth_schema() -> None:
    """Create and seed demo credentials for existing bank accounts."""
    global _AUTH_SCHEMA_READY
    if _AUTH_SCHEMA_READY:
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_user_credentials (
                user_id UUID PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_bank_user_credentials_username
            ON bank_user_credentials(username)
            """
        )
        cursor.execute(
            """
            SELECT ba.user_id
            FROM bank_accounts ba
            LEFT JOIN bank_user_credentials buc ON ba.user_id = buc.user_id
            WHERE buc.user_id IS NULL
            ORDER BY ba.created_at ASC, ba.user_id ASC
            """
        )
        missing_rows = cursor.fetchall()
        if missing_rows:
            cursor.execute("SELECT COUNT(*) FROM bank_user_credentials")
            existing_count = int(cursor.fetchone()[0] or 0)
            for index, (user_id,) in enumerate(missing_rows, start=existing_count + 1):
                password_hash, password_salt = new_password_hash(DEMO_BANK_PASSWORD)
                cursor.execute(
                    """
                    INSERT INTO bank_user_credentials (
                        user_id, username, password_hash, password_salt
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (str(user_id), f"user{index}", password_hash, password_salt),
                )
        conn.commit()
        _AUTH_SCHEMA_READY = True
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


SESSION_COOKIE = "bank_simulator_session"
SSO_ISSUER = "spectra"
SSO_AUDIENCE = "bank_simulator"
BANK_SSO_ISSUER = "bank_simulator"
BANK_SSO_AUDIENCE = "spectra"


def hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return digest.hex()


def new_password_hash(password: str) -> tuple[str, str]:
    salt_hex = secrets.token_bytes(16).hex()
    return hash_password(password, salt_hex), salt_hex


def verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    candidate = hash_password(password, stored_salt)
    return hmac.compare_digest(candidate, stored_hash)


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def sign_payload(payload: dict[str, Any]) -> str:
    body = b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(SSO_SHARED_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{b64url_encode(signature)}"


def verify_signed_payload(token: str) -> dict[str, Any] | None:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(SSO_SHARED_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    try:
        provided = b64url_decode(signature)
    except Exception:
        return None
    if not hmac.compare_digest(expected, provided):
        return None
    try:
        return json.loads(b64url_decode(body))
    except Exception:
        return None


def build_sso_token_for_spectra(user_id: str) -> str:
    now = int(datetime.now().timestamp())
    return sign_payload(
        {
            "sub": user_id,
            "iss": BANK_SSO_ISSUER,
            "aud": BANK_SSO_AUDIENCE,
            "iat": now,
            "exp": now + SSO_TOKEN_TTL_SECONDS,
            "nonce": secrets.token_urlsafe(16),
        }
    )


def verify_spectra_sso_payload(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    if payload.get("iss") != SSO_ISSUER or payload.get("aud") != SSO_AUDIENCE:
        return False
    return int(payload.get("exp", 0)) >= int(datetime.now().timestamp())


def read_session_user_id(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    payload = verify_signed_payload(token)
    if not payload or int(payload.get("exp", 0)) < int(datetime.now().timestamp()):
        return None
    user_id = str(payload.get("sub") or "").strip()
    return user_id or None


def set_session_cookie(response: Response, user_id: str) -> None:
    now = int(datetime.now().timestamp())
    response.set_cookie(
        SESSION_COOKIE,
        sign_payload(
            {
                "sub": user_id,
                "iat": now,
                "exp": now + SESSION_TTL_SECONDS,
                "nonce": secrets.token_urlsafe(12),
            }
        ),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
    )


def get_user_info(user_id: str) -> dict[str, Any] | None:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT
                ba.user_id,
                COALESCE(up.persona_type, 'Unknown') AS persona_type,
                ba.account_number,
                ba.bank_name,
                ba.balance,
                COUNT(bt.id) as transaction_count,
                COUNT(CASE WHEN bt.is_anomaly THEN 1 END) as anomaly_count
            FROM bank_accounts ba
            LEFT JOIN user_personas up ON ba.user_id = up.user_id
            LEFT JOIN bank_transactions bt ON ba.user_id = bt.user_id
            WHERE ba.user_id = %s
            GROUP BY ba.user_id, up.persona_type, ba.account_number, ba.bank_name, ba.balance
            LIMIT 1
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        data = row_to_dict(cursor, row)
        return {
            "user_id": str(data["user_id"]),
            "persona_type": data["persona_type"],
            "account_number": data["account_number"],
            "bank_name": data["bank_name"],
            "current_balance": float(data["balance"]),
            "transaction_count": int(data["transaction_count"]),
            "anomaly_count": int(data["anomaly_count"]),
        }
    finally:
        cursor.close()
        conn.close()


def require_bank_user(request: Request, requested_user_id: str | None = None) -> str:
    session_user_id = read_session_user_id(request)
    if not session_user_id:
        auth = str(request.headers.get("authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            payload = verify_signed_payload(auth[7:].strip())
            if verify_spectra_sso_payload(payload):
                session_user_id = str(payload.get("sub") or "").strip()
    if not session_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if requested_user_id and str(requested_user_id) != session_user_id:
        raise HTTPException(status_code=403, detail="Cannot access another user's bank data")
    return session_user_id


def safe_bank_return_path(value: str | None) -> str:
    target = str(value or "").strip()
    if not target.startswith("/"):
        return "/dashboard"
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return "/dashboard"
    if not parsed.path.startswith(("/dashboard", "/sso/entry")):
        return "/dashboard"
    return target


def safe_spectra_return_url(value: str | None) -> str:
    fallback = f"{SPECTRA_BASE_URL}/sso/bank/callback"
    target = str(value or "").strip()
    if not target:
        return fallback
    parsed = urlparse(target)
    spectra = urlparse(SPECTRA_BASE_URL)
    if parsed.scheme not in {"http", "https"}:
        return fallback
    if parsed.netloc != spectra.netloc:
        return fallback
    if parsed.path != "/sso/bank/callback":
        return fallback
    return target


def append_token(url: str, token: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'token': token})}"


def verify_credentials(username: str, password: str) -> dict[str, Any] | None:
    ensure_auth_schema()
    normalized_username = str(username or "").strip().lower()
    if not normalized_username or not password:
        return None

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT
                buc.user_id,
                buc.password_hash,
                buc.password_salt
            FROM bank_user_credentials buc
            WHERE lower(buc.username) = %s
            LIMIT 1
            """,
            (normalized_username,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        user_id, password_hash, password_salt = row
        if not verify_password(password, str(password_hash), str(password_salt)):
            return None
        return get_user_info(str(user_id))
    finally:
        cursor.close()
        conn.close()


def get_demo_users(limit: int = 100) -> list[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT
                ba.user_id,
                COALESCE(up.persona_type, 'Unknown') AS persona_type,
                ba.account_number,
                ba.bank_name,
                ba.balance,
                COUNT(bt.id) as transaction_count,
                COUNT(CASE WHEN bt.is_anomaly THEN 1 END) as anomaly_count
            FROM bank_accounts ba
            LEFT JOIN user_personas up ON ba.user_id = up.user_id
            LEFT JOIN bank_transactions bt ON ba.user_id = bt.user_id
            GROUP BY ba.user_id, up.persona_type, ba.account_number, ba.bank_name, ba.balance
            ORDER BY ba.balance DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        users = []
        for row in rows:
            data = row_to_dict(cursor, row)
            users.append(
                {
                    "user_id": str(data["user_id"]),
                    "persona_type": data["persona_type"] or "Unknown",
                    "account_number": data["account_number"],
                    "bank_name": data["bank_name"],
                    "current_balance": float(data["balance"]),
                    "transaction_count": int(data["transaction_count"]),
                    "anomaly_count": int(data["anomaly_count"]),
                }
            )
        return users
    finally:
        cursor.close()
        conn.close()


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root(request: Request):
    """Open the Bank Simulator UI."""
    if read_session_user_id(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "service": "Bank Simulator API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": [
            "/login",
            "/dashboard",
            "/transactions",
            "/summary",
            "/anomalies",
            "/prediction",
            "/users",
            "/stats"
        ]
    }


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, return_to: Optional[str] = Query(None)):
    if read_session_user_id(request):
        return RedirectResponse(url=safe_bank_return_path(return_to), status_code=303)
    safe_return_to = safe_bank_return_path(return_to)
    html = """
    <!doctype html>
    <html>
      <head>
        <title>Bank Simulator Login</title>
        <style>
          body { font-family: Inter, system-ui, sans-serif; margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f6f8fb; color: #17202a; }
          main { width: min(520px, calc(100% - 32px)); background: #fff; border: 1px solid #d9e2ec; border-radius: 8px; padding: 28px; box-shadow: 0 16px 40px rgba(15, 23, 42, .08); }
          h1 { margin: 0 0 8px; }
          p { color: #52606d; line-height: 1.5; }
          form { display: grid; gap: 12px; margin-top: 22px; }
          label { font-weight: 700; }
          input, button, a { min-height: 42px; border-radius: 6px; font: inherit; }
          input { border: 1px solid #bcccdc; padding: 8px 10px; background: #fff; color: #17202a; }
          button, a { border: 1px solid #1864ab; background: #1864ab; color: #fff; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; padding: 0 14px; text-decoration: none; }
          .secondary { background: #fff; color: #1864ab; margin-top: 10px; }
          .error { color: #b42318; min-height: 20px; }
          .hint { background: #f0f4f8; border: 1px solid #d9e2ec; padding: 10px; border-radius: 6px; color: #334e68; }
        </style>
      </head>
      <body>
        <main>
          <h1>Bank Simulator</h1>
          <p>Sign in with a seeded bank username and password to open the simulator dashboard.</p>
          <div class="hint">Demo credentials: <strong>user1</strong> / <strong>Bank@123456</strong></div>
          <form id="login-form">
            <label for="username">Username</label>
            <input id="username" name="username" autocomplete="username" placeholder="user1" required />
            <label for="password">Password</label>
            <input id="password" name="password" type="password" autocomplete="current-password" placeholder="Bank@123456" required />
            <button type="submit">Sign in</button>
            <div class="error" id="error"></div>
          </form>
          <a class="secondary" href="/sso/start">Login from Spectra</a>
        </main>
        <script>
          const error = document.querySelector('#error');
          const returnTo = __RETURN_TO__;

          document.querySelector('#login-form').addEventListener('submit', async (event) => {
            event.preventDefault();
            error.textContent = '';
            const res = await fetch('/login', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                username: document.querySelector('#username').value,
                password: document.querySelector('#password').value,
                return_to: returnTo
              })
            });
            if (!res.ok) {
              const data = await res.json().catch(() => ({}));
              error.textContent = data.error || data.detail || 'Login failed';
              return;
            }
            const data = await res.json();
            window.location.href = data.redirect_url || '/dashboard';
          });
        </script>
      </body>
    </html>
    """
    return html.replace("__RETURN_TO__", json.dumps(safe_return_to))


@app.post("/login")
async def login(request: Request):
    body = await request.json()
    user = verify_credentials(
        str(body.get("username") or ""),
        str(body.get("password") or ""),
    )
    if not user:
        return JSONResponse({"error": "Invalid username or password"}, status_code=401)
    redirect_url = safe_bank_return_path(str(body.get("return_to") or ""))
    response = JSONResponse({"ok": True, "user": user, "redirect_url": redirect_url})
    set_session_cookie(response, user["user_id"])
    return response


@app.get("/sso/start")
async def sso_start():
    return RedirectResponse(url=f"{SPECTRA_BASE_URL}/sso/bank", status_code=303)


@app.get("/sso/entry", response_class=HTMLResponse)
async def sso_entry(request: Request, return_to: Optional[str] = Query(None)):
    session_user_id = read_session_user_id(request)
    safe_return_to = safe_spectra_return_url(return_to)
    if not session_user_id:
        bank_return = f"/sso/entry?{urlencode({'return_to': safe_return_to})}"
        return RedirectResponse(url=f"/login?return_to={quote(bank_return, safe='')}", status_code=303)

    user = get_user_info(session_user_id)
    if not user:
        response = RedirectResponse(url="/login", status_code=303)
        clear_session_cookie(response)
        return response

    html = """
    <!doctype html>
    <html>
      <head>
        <title>Bank SSO Consent</title>
        <style>
          body { font-family: Inter, system-ui, sans-serif; margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f6f8fb; color: #17202a; }
          main { width: min(520px, calc(100% - 32px)); background: #fff; border: 1px solid #d9e2ec; border-radius: 8px; padding: 28px; box-shadow: 0 16px 40px rgba(15, 23, 42, .08); }
          h1 { margin: 0 0 8px; }
          p { color: #52606d; line-height: 1.5; }
          .profile { background: #f0f4f8; border: 1px solid #d9e2ec; border-radius: 6px; padding: 12px; margin: 18px 0; }
          .actions { display: flex; gap: 10px; }
          button, a { min-height: 42px; border-radius: 6px; border: 1px solid #1864ab; font: inherit; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; padding: 0 14px; text-decoration: none; flex: 1; }
          .primary { background: #1864ab; color: #fff; }
          .secondary { background: #fff; color: #1864ab; }
          .error { color: #b42318; min-height: 20px; margin-top: 12px; }
        </style>
      </head>
      <body>
        <main>
          <h1>Confirm Bank Login</h1>
          <p>Spectra is requesting access using your current Bank Simulator session.</p>
          <div class="profile">
            <strong>__PERSONA__</strong><br />
            __BANK__ - __ACCOUNT__
          </div>
          <p>Do you want to continue as this user?</p>
          <div class="actions">
            <button class="primary" id="confirm">Yes, continue</button>
            <a class="secondary" href="/dashboard">No, stay here</a>
          </div>
          <div class="error" id="error"></div>
        </main>
        <script>
          const returnTo = __RETURN_TO__;
          document.querySelector('#confirm').addEventListener('click', async () => {
            const res = await fetch('/sso/confirm', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ consent: true, return_to: returnTo })
            });
            if (!res.ok) {
              const data = await res.json().catch(() => ({}));
              document.querySelector('#error').textContent = data.error || data.detail || 'Could not continue';
              return;
            }
            const data = await res.json();
            window.location.href = data.redirect_url || '/dashboard';
          });
        </script>
      </body>
    </html>
    """
    return (
        html.replace("__RETURN_TO__", json.dumps(safe_return_to))
        .replace("__PERSONA__", html_lib.escape(str(user["persona_type"])))
        .replace("__BANK__", html_lib.escape(str(user["bank_name"])))
        .replace("__ACCOUNT__", html_lib.escape(str(user["account_number"])))
    )


@app.post("/sso/confirm")
async def sso_confirm(request: Request):
    user_id = read_session_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json()
    if not bool(body.get("consent")):
        return {"ok": True, "redirect_url": "/dashboard"}

    return_to = safe_spectra_return_url(str(body.get("return_to") or ""))
    token = build_sso_token_for_spectra(user_id)
    return {"ok": True, "redirect_url": append_token(return_to, token)}


@app.get("/sso/callback")
async def sso_callback(token: str = Query(...)):
    payload = verify_signed_payload(token)
    now = int(datetime.now().timestamp())
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid SSO token")
    if payload.get("iss") != SSO_ISSUER or payload.get("aud") != SSO_AUDIENCE:
        raise HTTPException(status_code=401, detail="Invalid SSO token audience")
    if int(payload.get("exp", 0)) < now:
        raise HTTPException(status_code=401, detail="Expired SSO token")

    user_id = str(payload.get("sub") or "").strip()
    if not user_id or not get_user_info(user_id):
        raise HTTPException(status_code=401, detail="Unknown SSO user")

    response = RedirectResponse(url="/dashboard", status_code=303)
    set_session_cookie(response, user_id)
    return response


@app.post("/logout")
async def logout():
    response = JSONResponse({"ok": True})
    clear_session_cookie(response)
    return response


@app.get("/me")
async def me(request: Request):
    user_id = read_session_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_user_info(user_id)
    if not user:
        response = JSONResponse({"error": "Session user no longer exists"}, status_code=401)
        clear_session_cookie(response)
        return response
    return {"user": user}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    if not read_session_user_id(request):
        return RedirectResponse(url="/login", status_code=303)
    return """
    <!doctype html>
    <html>
      <head>
        <title>Bank Simulator Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
          :root { color-scheme: light; }
          * { box-sizing: border-box; }
          body { margin: 0; font-family: Inter, system-ui, sans-serif; background: #f6f8fb; color: #17202a; }
          header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 28px; background: #fff; border-bottom: 1px solid #d9e2ec; position: sticky; top: 0; z-index: 2; }
          h1, h2, h3, p { margin-top: 0; }
          h1 { font-size: 22px; margin-bottom: 4px; }
          h2 { font-size: 16px; margin-bottom: 14px; }
          main { width: min(1180px, calc(100% - 32px)); margin: 24px auto 40px; display: grid; gap: 18px; }
          .muted { color: #52606d; }
          .grid { display: grid; gap: 16px; grid-template-columns: repeat(4, minmax(0, 1fr)); }
          .two-col { display: grid; gap: 16px; grid-template-columns: 1.2fr .8fr; }
          .card { background: #fff; border: 1px solid #d9e2ec; border-radius: 8px; padding: 18px; box-shadow: 0 10px 28px rgba(15, 23, 42, .05); }
          .metric { display: grid; gap: 5px; }
          .metric span { color: #52606d; font-size: 13px; }
          .metric strong { font-size: 22px; }
          button, a.button { min-height: 38px; padding: 8px 13px; border-radius: 6px; border: 1px solid #bcccdc; background: #fff; color: #17202a; font: inherit; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; }
          .primary { background: #1864ab; border-color: #1864ab; color: #fff; }
          .actions { display: flex; gap: 10px; align-items: center; }
          table { width: 100%; border-collapse: collapse; }
          th, td { padding: 10px 8px; border-bottom: 1px solid #edf2f7; text-align: left; font-size: 14px; vertical-align: top; }
          th { color: #52606d; font-weight: 700; }
          .pill { display: inline-flex; align-items: center; min-height: 24px; padding: 2px 8px; border-radius: 999px; background: #edf2f7; color: #334e68; font-size: 12px; }
          .danger { background: #fff1f0; color: #b42318; }
          .positive { color: #137333; }
          .negative { color: #b42318; }
          .bars { display: grid; gap: 10px; }
          .bar-row { display: grid; gap: 6px; }
          .bar-label { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
          .bar { height: 8px; background: #edf2f7; border-radius: 999px; overflow: hidden; }
          .bar > div { height: 100%; background: #1864ab; }
          .error { background: #fff1f0; color: #b42318; border: 1px solid #ffccc7; padding: 12px; border-radius: 6px; display: none; }
          @media (max-width: 900px) { .grid, .two-col { grid-template-columns: 1fr; } header { align-items: flex-start; flex-direction: column; } .actions { width: 100%; } .actions > * { flex: 1; } }
        </style>
      </head>
      <body>
        <header>
          <div>
            <h1>Bank Simulator</h1>
            <div class="muted" id="profile-line">Loading profile...</div>
          </div>
          <div class="actions">
            <a class="button" href="/docs">API Docs</a>
            <button id="logout">Logout</button>
          </div>
        </header>

        <main>
          <div class="error" id="error"></div>

          <section class="grid">
            <div class="card metric"><span>Current balance</span><strong id="balance">-</strong></div>
            <div class="card metric"><span>90d spending</span><strong id="spending">-</strong></div>
            <div class="card metric"><span>90d income</span><strong id="income">-</strong></div>
            <div class="card metric"><span>Anomalies</span><strong id="anomaly-count">-</strong></div>
          </section>

          <section class="two-col">
            <div class="card">
              <h2>Spending by category</h2>
              <div class="bars" id="categories"></div>
            </div>
            <div class="card">
              <h2>Balance prediction</h2>
              <p><strong id="predicted-balance">-</strong></p>
              <p class="muted" id="prediction-detail">-</p>
              <p id="recommendation">-</p>
            </div>
          </section>

          <section class="two-col">
            <div class="card">
              <h2>Recent transactions</h2>
              <table>
                <thead><tr><th>Date</th><th>Merchant</th><th>Category</th><th>Amount</th></tr></thead>
                <tbody id="transactions"></tbody>
              </table>
            </div>
            <div class="card">
              <h2>Anomalies</h2>
              <table>
                <thead><tr><th>Merchant</th><th>Severity</th><th>Amount</th></tr></thead>
                <tbody id="anomalies"></tbody>
              </table>
            </div>
          </section>
        </main>

        <script>
          const money = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 });
          const dateFmt = new Intl.DateTimeFormat('vi-VN', { year: 'numeric', month: '2-digit', day: '2-digit' });
          const $ = (id) => document.getElementById(id);
          const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
          })[char]);

          async function api(path, options = {}) {
            const res = await fetch(path, options);
            if (res.status === 401) {
              window.location.href = '/login';
              return null;
            }
            if (!res.ok) {
              const data = await res.json().catch(() => ({}));
              throw new Error(data.error || data.detail || `Request failed: ${res.status}`);
            }
            return res.json();
          }

          function renderCategories(categories) {
            if (!categories.length) {
              $('categories').innerHTML = '<p class="muted">No spending categories in this period.</p>';
              return;
            }
            $('categories').innerHTML = categories.slice(0, 8).map((item) => `
              <div class="bar-row">
                <div class="bar-label"><span>${escapeHtml(item.category)}</span><strong>${money.format(item.total_amount)}</strong></div>
                <div class="bar"><div style="width: ${Math.min(item.percentage, 100)}%"></div></div>
              </div>
            `).join('');
          }

          function renderTransactions(rows) {
            $('transactions').innerHTML = rows.map((tx) => `
              <tr>
                <td>${dateFmt.format(new Date(tx.created_at))}</td>
                <td>${escapeHtml(tx.merchant)}<br><span class="muted">${escapeHtml(tx.payment_method || '')}</span></td>
                <td><span class="pill">${escapeHtml(tx.category)}</span></td>
                <td class="${tx.transaction_type === 'credit' ? 'positive' : 'negative'}">${tx.transaction_type === 'credit' ? '+' : '-'}${money.format(tx.amount)}</td>
              </tr>
            `).join('');
          }

          function renderAnomalies(rows) {
            if (!rows.length) {
              $('anomalies').innerHTML = '<tr><td colspan="3" class="muted">No anomalies found.</td></tr>';
              return;
            }
            $('anomalies').innerHTML = rows.slice(0, 8).map((row) => `
              <tr>
                <td>${escapeHtml(row.merchant)}<br><span class="muted">${escapeHtml(row.category)}</span></td>
                <td><span class="pill danger">${escapeHtml(row.severity)}</span></td>
                <td>${money.format(row.amount)}</td>
              </tr>
            `).join('');
          }

          async function loadDashboard() {
            try {
              const [me, summary, prediction, anomalies, transactions] = await Promise.all([
                api('/me'),
                api('/summary?days=90'),
                api('/prediction'),
                api('/anomalies?limit=8'),
                api('/transactions?limit=12'),
              ]);
              if (!me) return;
              const user = me.user;
              $('profile-line').textContent = `${user.persona_type} - ${user.bank_name} - ${user.account_number}`;
              $('balance').textContent = money.format(user.current_balance);
              $('spending').textContent = money.format(summary.total_spending);
              $('income').textContent = money.format(summary.total_income);
              $('anomaly-count').textContent = user.anomaly_count;
              $('predicted-balance').textContent = money.format(prediction.predicted_end_of_month_balance);
              $('prediction-detail').textContent = `${money.format(prediction.avg_daily_spending)} avg daily spending - ${prediction.days_remaining} days remaining - ${prediction.spending_trend}`;
              $('recommendation').textContent = prediction.recommendation;
              renderCategories(summary.categories || []);
              renderTransactions(transactions || []);
              renderAnomalies(anomalies || []);
            } catch (err) {
              $('error').style.display = 'block';
              $('error').textContent = err.message || 'Could not load dashboard';
            }
          }

          $('logout').addEventListener('click', async () => {
            await fetch('/logout', { method: 'POST' });
            window.location.href = '/login';
          });

          loadDashboard();
        </script>
      </body>
    </html>
    """


@app.get("/transactions", response_model=List[Transaction])
async def get_transactions(
    request: Request,
    user_id: Optional[str] = Query(None, description="UUID của user"),
    limit: int = Query(100, ge=1, le=1000, description="Số lượng transactions tối đa"),
    offset: int = Query(0, ge=0, description="Offset cho pagination"),
    category: Optional[str] = Query(None, description="Filter theo category"),
    start_date: Optional[str] = Query(None, description="Ngày bắt đầu (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Ngày kết thúc (YYYY-MM-DD)")
):
    """
    Lấy danh sách transactions của user
    
    - **user_id**: UUID của user
    - **limit**: Số lượng records tối đa (default: 100)
    - **offset**: Offset cho pagination (default: 0)
    - **category**: Filter theo category (optional)
    - **start_date**: Filter từ ngày (optional)
    - **end_date**: Filter đến ngày (optional)
    """
    user_id = require_bank_user(request, user_id)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query
        query = """
            SELECT 
                id, user_id, account_id, transaction_type, amount, merchant,
                merchant_category, category, description, balance_after,
                is_anomaly, anomaly_reason, location, payment_method,
                reference_number, created_at
            FROM bank_transactions
            WHERE user_id = %s
        """
        params = [user_id]
        
        if category:
            query += " AND category = %s"
            params.append(category)
        
        if start_date:
            query += " AND created_at >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND created_at <= %s"
            params.append(end_date)
        
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        transactions = []
        for row in rows:
            tx_dict = row_to_dict(cursor, row)
            transactions.append(Transaction(**tx_dict))
        
        cursor.close()
        conn.close()
        
        return transactions
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/summary", response_model=SpendingSummary)
async def get_spending_summary(
    request: Request,
    user_id: Optional[str] = Query(None, description="UUID của user"),
    days: int = Query(90, ge=1, le=365, description="Số ngày để tính summary")
):
    """
    Lấy tổng quan chi tiêu của user theo category
    
    - **user_id**: UUID của user
    - **days**: Số ngày để tính summary (default: 90)
    """
    user_id = require_bank_user(request, user_id)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Get category breakdown
        cursor.execute("""
            SELECT 
                category,
                SUM(amount) as total_amount,
                COUNT(*) as transaction_count,
                AVG(amount) as avg_amount
            FROM bank_transactions
            WHERE user_id = %s 
                AND transaction_type = 'debit'
                AND created_at >= %s
            GROUP BY category
            ORDER BY total_amount DESC
        """, (user_id, start_date))
        
        category_rows = cursor.fetchall()
        
        # Calculate totals
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN transaction_type = 'debit' THEN amount ELSE 0 END) as total_spending,
                SUM(CASE WHEN transaction_type = 'credit' THEN amount ELSE 0 END) as total_income
            FROM bank_transactions
            WHERE user_id = %s AND created_at >= %s
        """, (user_id, start_date))
        
        totals = cursor.fetchone()
        total_spending = float(totals[0] or 0)
        total_income = float(totals[1] or 0)
        
        # Build category summaries
        categories = []
        for row in category_rows:
            # row = (category, total_amount, transaction_count, avg_amount)
            category_name = row[0]
            total_amount = float(row[1])
            transaction_count = int(row[2])
            avg_amount = float(row[3])
            
            categories.append(CategorySummary(
                category=category_name,
                total_amount=total_amount,
                transaction_count=transaction_count,
                avg_amount=avg_amount,
                percentage=(total_amount / total_spending * 100) if total_spending > 0 else 0
            ))
        
        cursor.close()
        conn.close()
        
        return SpendingSummary(
            user_id=user_id,
            total_spending=total_spending,
            total_income=total_income,
            net_cashflow=total_income - total_spending,
            categories=categories,
            period_days=days
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/anomalies", response_model=List[AnomalyTransaction])
async def get_anomalies(
    request: Request,
    user_id: Optional[str] = Query(None, description="UUID của user"),
    limit: int = Query(50, ge=1, le=200, description="Số lượng anomalies tối đa")
):
    """
    Lấy danh sách giao dịch bất thường (anomalies)
    
    - **user_id**: UUID của user
    - **limit**: Số lượng records tối đa (default: 50)
    """
    user_id = require_bank_user(request, user_id)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                id, amount, merchant, category, anomaly_reason, created_at
            FROM bank_transactions
            WHERE user_id = %s AND is_anomaly = TRUE
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, limit))
        
        rows = cursor.fetchall()
        
        anomalies = []
        for row in rows:
            tx_dict = row_to_dict(cursor, row)
            
            # Determine severity based on amount
            amount = float(tx_dict["amount"])
            if amount > 10_000_000:
                severity = "high"
            elif amount > 1_000_000:
                severity = "medium"
            else:
                severity = "low"
            
            anomalies.append(AnomalyTransaction(
                id=tx_dict["id"],
                amount=amount,
                merchant=tx_dict["merchant"],
                category=tx_dict["category"],
                anomaly_reason=tx_dict["anomaly_reason"],
                created_at=tx_dict["created_at"],
                severity=severity
            ))
        
        cursor.close()
        conn.close()
        
        return anomalies
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/prediction", response_model=PredictionResponse)
async def get_balance_prediction(
    request: Request,
    user_id: Optional[str] = Query(None, description="UUID của user")
):
    """
    Dự đoán số dư cuối tháng dựa trên pattern chi tiêu
    
    - **user_id**: UUID của user
    """
    user_id = require_bank_user(request, user_id)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get current balance
        cursor.execute("""
            SELECT balance
            FROM bank_accounts
            WHERE user_id = %s
            LIMIT 1
        """, (user_id,))
        
        balance_row = cursor.fetchone()
        if not balance_row:
            raise HTTPException(status_code=404, detail="User not found")
        
        current_balance = float(balance_row[0])
        
        # Calculate average daily spending (last 30 days)
        cursor.execute("""
            SELECT 
                SUM(amount) / 30.0 as avg_daily_spending,
                COUNT(*) as tx_count
            FROM bank_transactions
            WHERE user_id = %s 
                AND transaction_type = 'debit'
                AND created_at >= NOW() - INTERVAL '30 days'
        """, (user_id,))
        
        spending_row = cursor.fetchone()
        avg_daily_spending = float(spending_row[0] or 0)
        
        # Calculate spending trend (compare last 15 days vs previous 15 days)
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN created_at >= NOW() - INTERVAL '15 days' THEN amount ELSE 0 END) as recent,
                SUM(CASE WHEN created_at < NOW() - INTERVAL '15 days' AND created_at >= NOW() - INTERVAL '30 days' THEN amount ELSE 0 END) as previous
            FROM bank_transactions
            WHERE user_id = %s AND transaction_type = 'debit'
        """, (user_id,))
        
        trend_row = cursor.fetchone()
        recent_spending = float(trend_row[0] or 0)
        previous_spending = float(trend_row[1] or 0)
        
        if previous_spending > 0:
            trend_ratio = recent_spending / previous_spending
            if trend_ratio > 1.1:
                spending_trend = "increasing"
            elif trend_ratio < 0.9:
                spending_trend = "decreasing"
            else:
                spending_trend = "stable"
        else:
            spending_trend = "stable"
        
        # Calculate days remaining in month
        now = datetime.now()
        last_day = (now.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        days_remaining = (last_day - now).days
        
        # Predict end of month balance
        predicted_spending = avg_daily_spending * days_remaining
        predicted_balance = current_balance - predicted_spending
        
        # Generate recommendation
        if predicted_balance < 0:
            recommendation = "⚠️ Cảnh báo: Số dư dự kiến âm. Hãy giảm chi tiêu hoặc tăng thu nhập."
        elif predicted_balance < current_balance * 0.2:
            recommendation = "⚡ Lưu ý: Số dư cuối tháng thấp. Nên kiểm soát chi tiêu."
        elif spending_trend == "increasing":
            recommendation = "📈 Chi tiêu đang tăng. Hãy xem xét các khoản chi không cần thiết."
        else:
            recommendation = "✅ Tài chính ổn định. Tiếp tục duy trì thói quen tốt."
        
        cursor.close()
        conn.close()
        
        return PredictionResponse(
            user_id=user_id,
            current_balance=current_balance,
            predicted_end_of_month_balance=predicted_balance,
            avg_daily_spending=avg_daily_spending,
            days_remaining=days_remaining,
            spending_trend=spending_trend,
            recommendation=recommendation
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/users", response_model=List[UserInfo])
async def get_all_users(
    limit: int = Query(50, ge=1, le=100, description="Số lượng users tối đa"),
    persona_type: Optional[str] = Query(None, description="Filter theo persona type")
):
    """
    Lấy danh sách tất cả users
    
    - **limit**: Số lượng users tối đa (default: 50)
    - **persona_type**: Filter theo persona (Student, Office Worker, High-Net-Worth)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                ba.user_id,
                up.persona_type,
                ba.account_number,
                ba.bank_name,
                ba.balance,
                COUNT(bt.id) as transaction_count,
                COUNT(CASE WHEN bt.is_anomaly THEN 1 END) as anomaly_count
            FROM bank_accounts ba
            LEFT JOIN user_personas up ON ba.user_id = up.user_id
            LEFT JOIN bank_transactions bt ON ba.user_id = bt.user_id
        """
        
        params = []
        if persona_type:
            query += " WHERE up.persona_type = %s"
            params.append(persona_type)
        
        query += """
            GROUP BY ba.user_id, up.persona_type, ba.account_number, ba.bank_name, ba.balance
            ORDER BY ba.balance DESC
            LIMIT %s
        """
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        users = []
        for row in rows:
            user_dict = row_to_dict(cursor, row)
            users.append(UserInfo(
                user_id=user_dict["user_id"],
                persona_type=user_dict["persona_type"] or "Unknown",
                account_number=user_dict["account_number"],
                bank_name=user_dict["bank_name"],
                current_balance=float(user_dict["balance"]),
                transaction_count=int(user_dict["transaction_count"]),
                anomaly_count=int(user_dict["anomaly_count"])
            ))
        
        cursor.close()
        conn.close()
        
        return users
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/stats", response_model=OverallStats)
async def get_overall_stats():
    """
    Lấy thống kê tổng quan của toàn bộ hệ thống
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Total users
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM bank_accounts")
        total_users = cursor.fetchone()[0]
        
        # Total transactions
        cursor.execute("SELECT COUNT(*) FROM bank_transactions")
        total_transactions = cursor.fetchone()[0]
        
        # Total anomalies
        cursor.execute("SELECT COUNT(*) FROM bank_transactions WHERE is_anomaly = TRUE")
        total_anomalies = cursor.fetchone()[0]
        
        # Total volume
        cursor.execute("SELECT SUM(amount) FROM bank_transactions WHERE transaction_type = 'debit'")
        total_volume = float(cursor.fetchone()[0] or 0)
        
        # Personas distribution
        cursor.execute("""
            SELECT persona_type, COUNT(*) as count
            FROM user_personas
            GROUP BY persona_type
        """)
        persona_rows = cursor.fetchall()
        personas = {row[0]: row[1] for row in persona_rows}
        
        cursor.close()
        conn.close()
        
        anomaly_rate = (total_anomalies / total_transactions * 100) if total_transactions > 0 else 0
        
        return OverallStats(
            total_users=total_users,
            total_transactions=total_transactions,
            total_anomalies=total_anomalies,
            anomaly_rate=anomaly_rate,
            total_volume=total_volume,
            personas=personas
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 80)
    print("Bank Simulator API Server")
    print("=" * 80)
    print(f"Starting on: http://{API_HOST}:{API_PORT}")
    print(f"API Docs: http://localhost:{API_PORT}/docs")
    print(f"Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'configured'}")
    print("=" * 80)
    uvicorn.run(app, host=API_HOST, port=API_PORT)
