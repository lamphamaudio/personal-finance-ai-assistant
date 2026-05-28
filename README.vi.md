# Personal Finance AI Assistant

Trình quản lý và phân tích tài chính cá nhân cục bộ, bảo mật và thông minh, tích hợp trí tuệ nhân tạo (AI) chạy offline 100%.

## Các tính năng nổi bật

- **Bảo mật & Cục bộ 100%**: Toàn bộ dữ liệu của bạn được lưu trữ và xử lý cục bộ trên máy tính dưới dạng cơ sở dữ liệu SQLite (`data/prism.db`). Sao kê ngân hàng của bạn không bao giờ bị gửi lên internet.
- **Phân loại giao dịch bằng Học máy (AI Offline)**: Tự động "làm sạch" tên cửa hàng từ sao kê thô và đoán danh mục chi tiêu chính xác thông qua mô hình học máy cục bộ (TF-IDF + Logistic Regression). AI tự động học hỏi từ mỗi lần bạn sửa đổi để ngày càng thông minh hơn.
- **Theo dõi Ngân sách & Chu kỳ**: Thiết lập hạn mức chi tiêu hàng tháng theo chu kỳ lương của bạn và nhận cảnh báo trực quan bằng các nhãn màu sắc (🟢/🟡/🔴).
- **Giao diện Web tuyệt đẹp**: Hỗ trợ đầy đủ hai giao diện Sáng/Tối (Light/Dark Mode) mượt mà tại `http://localhost:8081`, bao gồm:
  * **Tổng quan**: Theo dõi dòng tiền, dự báo tốc độ chi tiêu (burn-rate) và phân tích biểu đồ trực quan.
  * **Sổ giao dịch**: Bộ lọc tìm kiếm thông minh, hỗ trợ chỉnh sửa trực tiếp tên cửa hàng và danh mục.
  * **Tải lên sao kê**: Kéo thả file CSV, PDF, hoặc OFX để AI xử lý tức thì, có chế độ duyệt thông minh trước khi lưu.
  * **Định kỳ (Subscriptions)**: Tự động gom nhóm và phát hiện các dịch vụ đăng ký hàng tháng (Netflix, Spotify...) và cảnh báo khi có biến động giá.

## Hướng dẫn khởi chạy nhanh

### 1. Cài đặt môi trường ảo

Đảm bảo máy tính của bạn đã cài [uv](https://github.com/astral-sh/uv), sau đó đồng bộ thư viện:

```bash
uv sync --locked
```

### 2. Khởi chạy Web Dashboard

Chạy lệnh sau trong terminal:

```bash
uv run python -m spectra --serve --port 8081
```

Truy cập ngay **[http://localhost:8081](http://localhost:8081)** trên trình duyệt của bạn!

*Lưu ý: Trong lần đầu tiên truy cập, bạn hãy vào trang **Cài đặt (Settings)** để chọn Tiền tệ gốc là **VND** trước khi tải lên sao kê ngân hàng.*
