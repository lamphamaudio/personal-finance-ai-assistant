# Spectra cho người Việt

Spectra là dashboard tài chính cá nhân chạy cục bộ. Ứng dụng đọc sao kê ngân hàng dạng CSV/PDF/OFX, phân loại giao dịch, theo dõi ngân sách, chi tiêu định kỳ và xu hướng theo tháng.

## Chạy native bằng uv

```powershell
cd D:\AiClone\Spectra
uv sync --locked
$env:PYTHONUTF8='1'
uv run python -m spectra --serve
```

Mở `http://localhost:8080`.

## Cấu hình mặc định

```env
AI_PROVIDER=local
BASE_CURRENCY=VND
LOG_LEVEL=INFO
```

`local` chạy offline và không cần API key. Nếu muốn dùng OpenAI:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5-nano
BASE_CURRENCY=VND
```

## File mẫu

File test có sẵn tại `inbox/fake_transactions_may_2026.csv`, dùng VND và merchant phổ biến tại Việt Nam như Grab, Shopee, WinMart, EVN, Viettel, Highlands, Pharmacity.

Dry-run:

```powershell
$env:PYTHONUTF8='1'
uv run python -m spectra -f inbox\fake_transactions_may_2026.csv --dry-run
```

## Sao kê ngân hàng Việt

Parser ưu tiên các cột phổ biến:

- `Ngày giao dịch`, `Ngày hiệu lực`, `Ngày hạch toán`
- `Nội dung`, `Mô tả`, `Diễn giải`
- `Số tiền`, `Ghi nợ`, `Ghi có`
- `Đối tác`, `Tài khoản đối ứng`
- `Loại tiền`

V1 tập trung CSV/PDF/OFX. XLSX sẽ cần thêm parser riêng khi có file mẫu thực tế.
