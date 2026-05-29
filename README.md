# Personal Finance AI Assistant

An elegant personal finance dashboard that helps you automate, categorize, and track your financial health with a Supabase/Postgres backend.

## Key Features

- **Private Backend Storage**: Financial data is stored in your Postgres database. Supabase is supported through `DATABASE_URL`; the frontend does not connect to Supabase directly.
- **Offline ML Categorization**: Uses an intelligent local Machine Learning engine (TF-IDF + Logistic Regression) that auto-cleans transaction descriptions, predicts categories, and learns from your manual corrections over time.
- **Dynamic Budgets & Cycles**: Track your expenses against customizable financial cycles (e.g., salary paydays) with live status indicators (🟢/🟡/🔴).
- **Interactive Web Dashboard**: An elegant dark/light theme interface at `http://localhost:8081` featuring:
  - **Overview**: High-level burn-rate projections, net cash flows, and category distributions.
  - **Transactions Ledger**: Searchable, paginated history with inline merchant & category editing.
  - **Smart Upload**: Drag-and-drop CSV, PDF, or OFX statements with inline suggestions and bulk edits.
  - **Trends**: Month-over-month and year-over-year spending breakdowns.
  - **Subscriptions Tracker**: Automatically detects recurring subscriptions (Netflix, Spotify, etc.) and flags price increases.

## Quick Start (Local Python Mode)

### 1. Install Dependencies

Ensure you have [uv](https://github.com/astral-sh/uv) installed, then sync the virtual environment:

```bash
uv sync --locked
```

### 2. Configure Postgres

Create a `.env` file and set your Supabase/Postgres connection string:

```bash
DATABASE_URL=postgresql://postgres.project-ref:password@aws-0-region.pooler.supabase.com:5432/postgres
AI_PROVIDER=local
BASE_CURRENCY=VND
```

Use a Supabase direct connection or Session Pooler for the long-running FastAPI server. Do not commit the real URL.

### 3. Run the Dashboard

Start the local web server:

```bash
uv run python -m spectra --serve --port 8081
```

Open **[http://localhost:8081](http://localhost:8081)** in your browser to get started!

*Note: On your first visit, navigate to the **Settings (Cài đặt)** page to set your **Base Currency (VND)** before importing your first bank statement.*
