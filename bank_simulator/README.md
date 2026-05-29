# Bank Simulator API

REST API cung cấp dữ liệu test cho Financial AI Advisor

## Khởi động

```bash
py main.py
```

Server: http://localhost:8000  
Docs: http://localhost:8000/docs

## API Endpoints

- `GET /` - Health check
- `GET /stats` - Statistics
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

Tạo 50 users với 100+ transactions mỗi user (last 3 months)
