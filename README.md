# Personal Finance AI Assistant

🏦 Hệ thống quản lý tài chính cá nhân với AI

**2 Services:**
- **Main Service (Spectra)** - Dashboard, AI categorization, Budget tracking → Port 8080 (hoặc 8081)
- **Bank Simulator** - REST API với dữ liệu test & local UI → Port 8000

Dùng chung **Supabase PostgreSQL Database**

---

## 🚀 Khởi động (Thủ công từng Terminal)

### 1. Cấu hình Environment (.env)
Trước khi chạy, hãy chuẩn bị các tệp cấu hình môi trường để kết nối database và các API cần thiết:
- Sao chép `.env.example` thành `.env` tại thư mục gốc của dự án.
- Sao chép `bank_simulator/.env.example` thành `bank_simulator/.env`.
- Cấu hình thông số trong hai tệp `.env` vừa tạo (đặc biệt là biến `DATABASE_URL` kết nối với Supabase PostgreSQL).

### 2. Khởi động các Services

Để chạy ứng dụng hoàn chỉnh, bạn mở 2 Terminal riêng biệt:

#### Terminal 1: Chạy Main Service (Spectra)
Bạn có thể chọn chạy trực tiếp bằng Python (sử dụng `uv` hoặc môi trường ảo `.venv`) hoặc chạy qua Docker.

**Cách A: Chạy trực tiếp bằng Python (Khuyên dùng)**
- Cài đặt dependencies (nếu chưa cài):
  ```bash
  # Nếu dùng uv:
  uv sync
  
  # Hoặc dùng pip:
  pip install -e .
  ```
- Khởi chạy Spectra:
  ```bash
  # Nếu dùng uv:
  uv run spectra --serve --port 8080
  
  # Hoặc dùng python trực tiếp:
  python -m spectra --serve --port 8080
  ```

**Cách B: Chạy qua Docker**
```bash
docker compose up --build
```
*(Nếu muốn chạy ở port khác cổng 8080 mặc định, thiết lập biến môi trường `SPECTRA_PORT` trước khi chạy docker compose)*

---

#### Terminal 2: Chạy Bank Simulator
Chạy simulator bằng python ở môi trường local:
```bash
cd bank_simulator
python main.py
```
*(Nếu sử dụng Windows launcher, có thể dùng lệnh `py main.py`)*

### 3. Truy cập các dịch vụ
- **Main Service (Spectra Dashboard):** [http://localhost:8080](http://localhost:8080) (hoặc cổng bạn cấu hình)
- **Bank Simulator (API Docs & UI):** [http://localhost:8000](http://localhost:8000) / [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 📊 Tính năng

### Main Service (Spectra)
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
├── .env                      ← Cấu hình môi trường cho Spectra
├── src/spectra/              ← Mã nguồn Main service (Spectra)
├── supabase/migrations/      ← Cấu hình và migration cho database Supabase
└── bank_simulator/           ← Dịch vụ giả lập ngân hàng (Bank Simulator)
    ├── .env                  ← Cấu hình môi trường cho Bank Simulator
    ├── main.py               ← API server & Dashboard của Bank Simulator
    └── data_seeder.py        ← Script tạo dữ liệu mẫu cho ngân hàng
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
