# Bank Simulator API

REST API cung cấp dữ liệu test cho Financial AI Advisor

## Khởi động

```bash
py main.py
```

Server: http://localhost:8000  
Docs: http://localhost:8000/docs

## Demo SSO

Bank Simulator accepts demo SSO from Spectra.

Required shared config in both service env files:

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

Open `http://localhost:8000` or `http://localhost:8000/login` and either:

- sign in with a seeded username/password, or
- continue from Spectra through the consent screen.

Default demo credentials:

```text
username: user1
password: Bank@123456
```

The app creates credentials for every seeded bank account as `user1`, `user2`, ... with the same demo password. Passwords are stored as PBKDF2-SHA256 hashes, not plaintext.

After login, Bank Simulator opens `http://localhost:8000/dashboard`, which shows:

- account profile and balance from `/me`
- spending summary from `/summary`
- balance prediction from `/prediction`
- anomaly list from `/anomalies`
- recent transactions from `/transactions`

## API Endpoints

- `GET /` - Open login/dashboard UI
- `GET /health` - Health check
- `GET /stats` - Statistics
- `GET /login` - Username/password login page
- `POST /login` - Username/password login
- `GET /dashboard` - Bank Simulator dashboard UI
- `GET /sso/start` - Redirect to Spectra SSO
- `GET /sso/entry` - SSO consent entry point from Spectra
- `POST /sso/confirm` - Confirm current Bank user and redirect back to Spectra
- `GET /sso/callback` - SSO callback
- `GET /me` - Current bank session user
- `POST /logout` - Clear bank session
- `GET /users` - List users
- `GET /transactions?user_id=...` - Transactions
- `GET /summary?user_id=...` - Summary
- `GET /anomalies?user_id=...` - Anomalies
- `GET /prediction?user_id=...` - Prediction

## Data

- 69 users
- 8,033 transactions
- 3 personas: Student, Office Worker, High-Net-Worth
- 386 anomalies (4.8%)

## Generate Data

```bash
py data_seeder.py
```

## Fill Missing Transactions

If existing bank accounts have no transactions, run:

```bash
.\.venv\Scripts\python.exe seed_missing_transactions.py
```

This only targets accounts with zero transactions and seeds realistic activity plus a few anomalies for dashboard demos.

Tạo 50 users với 100+ transactions mỗi user (last 3 months)
