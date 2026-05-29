# Personal Finance AI Assistant

🏦 Hệ thống quản lý tài chính cá nhân với AI

**2 Services:**
- **Main Service (Spectra)** - Dashboard, AI categorization, Budget tracking → Port 8081
- **Bank Simulator** - REST API với dữ liệu test → Port 8000

Dùng chung **Supabase PostgreSQL Database**

---

## 🚀 Khởi động

### Lần đầu tiên (Setup):
```bash
py setup.py
```

### Khởi động services:

**Cách 1: Tự mở 2 terminal (Đơn giản nhất)**

Terminal 1:
```bash
cd bank_simulator
py main.py
```

Terminal 2:
```bash
py -m spectra --serve --port 8081
```

**Cách 2: Double-click file .cmd**
- `start_bank_simulator.cmd`
- `start_main_service.cmd`

**Truy cập:**
- Main Service: http://localhost:8081
- Bank Simulator: http://localhost:8000/docs

---

## 📊 Tính năng

### Main Service (8081)
- Dashboard với charts
- Upload CSV/PDF/OFX
- AI categorization
- Budget tracking
- Trends analysis

### Bank Simulator (8000)
- REST API (6 endpoints)
- 69 users, 8,033 transactions
- 3 personas: Student, Office Worker, High-Net-Worth
- Anomaly detection (4.8%)
- Balance prediction

---

## 🗄️ Database

**Supabase PostgreSQL**

**Tables:**
- Main: `app_*` (8 tables)
- Bank Sim: `bank_*`, `user_*` (4 tables)

**Data:**
- 69 accounts
- 8,033 transactions
- 386 anomalies

---

## 🔧 API Endpoints

```
GET /                          Health check
GET /stats                     Statistics
GET /users                     List users
GET /transactions?user_id=...  Transactions
GET /summary?user_id=...       Summary
GET /anomalies?user_id=...     Anomalies
GET /prediction?user_id=...    Prediction
```

Docs: http://localhost:8000/docs

---

## 📁 Cấu trúc

```
personal-finance-ai-assistant/
├── run.py                    ← CHẠY FILE NÀY
├── .env                      ← Config
├── src/spectra/              ← Main service
├── supabase/migrations/      ← Database schemas
└── bank_simulator/           ← Bank simulator
    ├── .env
    ├── main.py               ← API server
    └── data_seeder.py        ← Data generator
```

---

## 🛠️ Troubleshooting

**Port đã dùng:**
```bash
netstat -ano | findstr :8081
taskkill /PID <PID> /F
```

**Database lỗi:**
Check `DATABASE_URL` trong `.env` và `bank_simulator/.env`

**Module not found:**
```bash
py -m pip install -e .
```

---

**Version:** 1.0.0 | **Status:** ✅ Production Ready
