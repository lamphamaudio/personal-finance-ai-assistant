# Personal Finance AI Assistant

An elegant, local-first personal finance dashboard that helps you automate, categorize, and track your financial health completely offline.

## Key Features

- **100% Offline & Private**: All data is processed and stored locally in a SQLite database (`data/prism.db`). Your bank statements never leave your computer.
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

### 2. Run the Dashboard

Start the local web server:

```bash
uv run python -m spectra --serve --port 8081
```

Open **[http://localhost:8081](http://localhost:8081)** in your browser to get started!

*Note: On your first visit, navigate to the **Settings (Cài đặt)** page to set your **Base Currency (VND)** before importing your first bank statement.*
