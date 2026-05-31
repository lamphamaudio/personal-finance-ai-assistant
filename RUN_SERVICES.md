# Run Services

This project has two local services:

- Spectra main app: `http://localhost:8081`
- Bank Simulator: `http://localhost:8000`

## 1. Required Env

Create/update `.env` at the repo root and `bank_simulator/.env` with the same SSO values:

```bash
SSO_SHARED_SECRET=change-me-for-local-demo
SPECTRA_BASE_URL=http://localhost:8081
BANK_SIMULATOR_BASE_URL=http://localhost:8000
SESSION_COOKIE_SECURE=false
SESSION_TTL_SECONDS=28800
SSO_TOKEN_TTL_SECONDS=300
DEMO_BANK_PASSWORD=Bank@123456
BANK_PASSWORD_ITERATIONS=210000
```

Both files also need a valid `DATABASE_URL`.

## 2. Start Spectra

From the repo root:

```powershell
uv run python -m spectra --serve --port 8081
```

Open:

```text
http://localhost:8081
```

## 3. Start Bank Simulator

From the repo root:

```powershell
cd bank_simulator
.\.venv\Scripts\python.exe main.py
```

Open:

```text
http://localhost:8000
```

API docs:

```text
http://localhost:8000/docs
```

## 4. Demo SSO Flow

1. Open `http://localhost:8081`.
2. Select a demo user and sign in.
3. Click `Open Bank Simulator`.
4. Spectra redirects to Bank Simulator SSO consent.
5. If Bank Simulator is not logged in, sign in with `user1` / `Bank@123456`.
6. Confirm using the current Bank Simulator user.
7. Bank Simulator redirects back to Spectra with a short-lived SSO token.

## 5. Stop Services

Find listeners:

```powershell
netstat -ano | findstr ":8081"
netstat -ano | findstr ":8000"
```

Stop by PID:

```powershell
Stop-Process -Id <PID> -Force
```
