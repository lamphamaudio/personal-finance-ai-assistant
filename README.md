# Personal Finance AI Assistant

Spectra là dashboard quản lý tài chính cá nhân có AI assistant tiếng Việt. Ứng dụng hỗ trợ nhập giao dịch ngân hàng demo, phân loại giao dịch, theo dõi ngân sách, mục tiêu tiết kiệm, phát hiện bất thường, dự báo số dư và hỏi đáp tài chính cá nhân qua chatbot.

## Trạng Thái

- Version package: `0.4.0`
- Trạng thái: Beta / MVP demo
- Backend: FastAPI + PostgreSQL/Supabase
- Frontend: React + Vite
- Bank demo: Bank Simulator local

## Dịch Vụ

- **Spectra main service**: dashboard, import, categorization, budget, trends, chatbot. Mặc định chạy ở `http://localhost:8080` hoặc `8081`.
- **Bank Simulator**: API và UI ngân hàng demo. Mặc định chạy ở `http://localhost:8000`.

Hai service dùng chung database PostgreSQL/Supabase qua `DATABASE_URL`.

## Cài Đặt

1. Tạo file `.env` từ `.env.example` ở thư mục gốc.
2. Cấu hình tối thiểu:

```bash
DATABASE_URL=postgresql://...
OPENAI_API_KEY=...
AI_PROVIDER=openai
```

3. Cài dependencies:

```bash
uv sync
```

4. Chạy Spectra:

```bash
uv run spectra --serve --port 8080
```

5. Chạy Bank Simulator ở terminal khác:

```bash
cd bank_simulator
python main.py
```

## Frontend

Chạy dev server:

```bash
cd frontend
npm install
npm run dev
```

Build frontend vào backend static bundle:

```bash
cd frontend
npm run build
```

## Tính Năng Chính

- Dashboard tổng quan chi tiêu, thu nhập, danh mục và merchant.
- Import giao dịch từ Bank Simulator hoặc file CSV/PDF/OFX.
- AI/local categorization và rule học từ chỉnh sửa của người dùng.
- Budget tracking, recommendation và what-if simulation.
- Savings goals, feasibility planning và progress tracking.
- Chatbot assistant có tool calling, confirmation flow, chat history và safe memory.
- Financial health score, anomaly explanation và balance forecast.

## Kiểm Thử

Backend:

```bash
uv run pytest -q
```

Frontend lint:

```bash
cd frontend
npm run lint
```

## Ghi Chú Bảo Mật MVP

- Chatbot chỉ dùng allowlisted tools.
- Write tools cần confirmation.
- Reset DB và admin/debug endpoints không được expose như chatbot tools.
- Demo auth dùng session cookie local, chưa phải mô hình production SaaS đầy đủ.
