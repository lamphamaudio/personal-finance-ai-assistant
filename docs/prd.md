# PRD — Spectra: Ứng dụng quản lý tài chính cá nhân với AI Chatbot tiếng Việt

### Thông tin tài liệu

| Tên sản phẩm      | Spectra — Personal Finance AI Assistant |
| ----------------- | --------------------------------------- |
| Phiên bản         | v0.4.0                                  |
| Tác giả           | Lam Pham                                |
| Cập nhật lần cuối | 28/06/2026                              |
| Trạng thái        | IN-REVIEW                               |

---

## Mục lục

1. [Tóm tắt điều hành](#1-tóm-tắt-điều-hành)
2. [Vấn đề khách hàng](#2-vấn-đề-khách-hàng)
3. [Khách hàng mục tiêu](#3-khách-hàng-mục-tiêu)
4. [Tổng quan giải pháp](#4-tổng-quan-giải-pháp)
5. [User Stories & Yêu cầu](#5-user-stories--yêu-cầu)
6. [Chỉ số thành công](#6-chỉ-số-thành-công)
7. [Rủi ro & Giả định](#7-rủi-ro--giả-định)
8. [Timeline & Milestones](#8-timeline--milestones)
9. [Stakeholders & Nhóm phát triển](#9-stakeholders--nhóm-phát-triển)
10. [Phụ lục](#phụ-lục)

---

# 1. Tóm tắt điều hành

Người Việt Nam, đặc biệt thế hệ 8X–9X đi làm, hiện thiếu công cụ quản lý tài chính cá nhân đơn giản và thông minh bằng tiếng Việt. Theo khảo sát nội bộ, hơn 70% người dùng mục tiêu vẫn ghi chép chi tiêu bằng Excel hoặc sổ tay, không có cảnh báo thời gian thực khi vượt ngân sách và không biết mình đang lãng phí tiền ở đâu.

**Spectra** là dashboard quản lý tài chính cá nhân kết hợp AI chatbot tiếng Việt — cho phép người dùng hỏi trực tiếp bằng tiếng Việt tự nhiên như _"Tháng này tôi tiêu nhiều nhất vào đâu?"_ hay _"Cuối tháng tôi còn bao nhiêu tiền?"_ và nhận câu trả lời chính xác dựa trên dữ liệu giao dịch thực của họ. Hệ thống kết hợp FastAPI backend, React frontend và LangGraph supervisor agent với bộ guardrails nhiều lớp đảm bảo an toàn tài chính.

**Phạm vi Phase 1 (Hiện tại):**

- AI Chatbot tiếng Việt với 30+ tools tài chính (read + write với confirmation flow)
- Dashboard tổng quan: chi tiêu, ngân sách, mục tiêu tiết kiệm, điểm sức khỏe tài chính
- Import sao kê (CSV / PDF / OFX) và phân loại tự động bằng LLM + rule engine
- Bank Simulator tích hợp SSO để demo và test toàn luồng
- Guardrails: từ chối tư vấn đầu tư, bảo vệ dữ liệu nhạy cảm, audit log

**Ngoài phạm vi Phase 1:** Ứng dụng mobile native, tích hợp ngân hàng thực (Open Banking), tư vấn đầu tư, đa người dùng / gia đình, mô hình SaaS production với billing.

**Mục tiêu:** Chatbot đạt Overall Pass Rate ≥ 90%, Intent Accuracy ≥ 95%, Confirmation Flow Accuracy 100%. Go-live nội bộ: Q3/2026.

---

# 2. Vấn đề khách hàng

## 2.1 Phát biểu vấn đề

### 2.1.1 Vấn đề người dùng cuối

| Nhóm vấn đề         | Tình trạng hiện tại                                                                                                              | Tác động                                                      |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| Theo dõi chi tiêu   | Người dùng ghi thủ công bằng Excel/sổ tay; dữ liệu phân tán nhiều ứng dụng ngân hàng                                             | Không có góc nhìn tổng hợp, tốn 1–2 giờ/tuần để đối chiếu     |
| Nhận thức tài chính | Không biết tháng này tiêu bao nhiêu, tiêu vào đâu cho đến khi cạn tiền                                                           | Quyết định chi tiêu mù quáng, vượt ngân sách mà không hay     |
| Lập kế hoạch        | Không có công cụ dự báo số dư, mô phỏng kịch bản (mua iPhone, tăng lương)                                                        | Mục tiêu tiết kiệm thất bại, không tích lũy được quỹ khẩn cấp |
| Ngôn ngữ            | Các app tài chính phổ biến (Mint, YNAB) không hỗ trợ tiếng Việt; chatbot AI chung (ChatGPT) không có dữ liệu thực của người dùng | Trải nghiệm xa cách, câu trả lời thiếu ngữ cảnh cá nhân       |

### 2.1.2 Vấn đề vận hành nội bộ

| Nhóm vấn đề        | Tình trạng hiện tại                                                            | Tác động                                |
| ------------------ | ------------------------------------------------------------------------------ | --------------------------------------- |
| Kiểm thử chatbot   | Không có bộ eval tự động — khó đo chất lượng sau mỗi lần cập nhật prompt/model | Rủi ro regression không phát hiện được  |
| Bảo mật write tool | Chatbot có thể ghi đè dữ liệu người dùng nếu không có xác nhận                 | Vi phạm dữ liệu, mất tin cậy người dùng |

## 2.2 Bằng chứng khách hàng

**Kết quả đánh giá chatbot (Evaluation Report — 2026-06-27)**

| Chỉ số                         | Giá trị hiện tại | Mục tiêu |
| ------------------------------ | ---------------- | -------- |
| Overall Pass Rate (LLM Judge)  | 84,2% (16/19)    | ≥ 90%    |
| Tool Selection Accuracy        | 94,7% (18/19)    | ≥ 90% ✅ |
| Intent Classification Accuracy | 100% (19/19)     | ≥ 90% ✅ |
| LLM-as-a-Judge Pass Rate       | 89,5% (17/19)    | ≥ 85% ✅ |

**Kết quả QA evaluation (27 scenarios — 2026-06-27)**

| Cấp độ                     | Câu    | Pass   | Xfail | Fail  | Tỷ lệ     |
| -------------------------- | ------ | ------ | ----- | ----- | --------- |
| ⭐ Dễ (Q01–Q05)            | 5      | 5      | 0     | 0     | 100%      |
| ⭐⭐ Trung bình (Q06–Q13)  | 8      | 8      | 0     | 0     | 100%      |
| ⭐⭐⭐ Khó (Q14–Q21)       | 8      | 8      | 0     | 0     | 100%      |
| ⭐⭐⭐⭐ Rất khó (Q22–Q25) | 4      | 3      | 1     | 0     | 75%       |
| 🔒 Safety (Q26–Q27)        | 2      | 2      | 0     | 0     | 100%      |
| **Tổng**                   | **27** | **26** | **1** | **0** | **96,3%** |

## 2.3 Bối cảnh tuân thủ & bảo mật

| Quy định / Nguyên tắc  | Nội dung                                                                                          | Tác động lên sản phẩm                                                     |
| ---------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Tư vấn tài chính       | Không được đưa ra khuyến nghị mua/bán cụ thể tài sản đầu tư (cổ phiếu, crypto)                    | Guardrail `InvestmentAdviceGuard` bắt buộc; từ chối mọi câu hỏi liên quan |
| Bảo vệ dữ liệu cá nhân | Không lộ số tài khoản, API key, UUID nội bộ trong phản hồi chatbot                                | `OutputGuard` + `redaction.py` chạy trên mọi response                     |
| Xác nhận hành động ghi | Mọi thao tác thay đổi dữ liệu (update category, create rule, update budget) phải qua bước confirm | Confirmation flow 2 bước bắt buộc với expiry 10 phút                      |

---

# 3. Khách hàng mục tiêu

## 3.1 Hồ sơ người dùng

**Persona chính — Nguyễn Văn A (Nhân viên văn phòng đi làm)**

| Thông tin           | Giá trị                                                              |
| ------------------- | -------------------------------------------------------------------- |
| Độ tuổi             | 24–35 tuổi                                                           |
| Thu nhập            | 10–25 triệu VND/tháng                                                |
| Chi tiêu trung bình | 60–80% thu nhập                                                      |
| Mục tiêu tài chính  | Mua xe, du lịch, xây quỹ khẩn cấp 3 tháng                            |
| Hành vi hiện tại    | Check app ngân hàng nhiều lần/ngày, không lập ngân sách              |
| Kênh                | Mobile-first, quen dùng Zalo/Messenger — tự nhiên với chat interface |

## 3.2 Hành trình người dùng

_Phase 1 tập trung vào: Onboarding → Import dữ liệu → Khám phá chatbot → Thực hiện hành động write (đặt ngân sách, tạo mục tiêu tiết kiệm)_

### 3.2.1 Luồng người dùng

1. **Đăng nhập** — SSO qua Bank Simulator (demo) hoặc tài khoản local
2. **Import sao kê** — Upload CSV/PDF/OFX → hệ thống tự phân loại → xem kết quả tại Transactions
3. **Hỏi chatbot** — Gõ câu hỏi tiếng Việt tự nhiên tại Chat Panel
4. **Xem dashboard** — Overview: chi tiêu, ngân sách, sức khỏe tài chính, mục tiêu
5. **Thực hiện hành động** — Chatbot gợi ý → hiện confirmation card → người dùng duyệt/hủy
6. **Theo dõi theo thời gian** — Trends, subscriptions, cashflow calendar

### 3.2.2 Luồng quản trị / vận hành

Priority xử lý guardrails (thứ tự fail-closed):

1. Input guard (PromptInjection, OutOfScope, InvestmentAdvice, SensitiveData)
2. Tool guard (UnregisteredTool → ScopeGuard → ParameterClamp → WriteConfirmation)
3. Output guard (CredentialLeak, PIILeak, DisclaimerEnforcer)

**Cấu hình tool (chat/tools.py):**

| Field            | Required | Mô tả                    | Ví dụ                 | Validation           |
| ---------------- | -------- | ------------------------ | --------------------- | -------------------- |
| `name`           | ✅       | Tên tool trong allowlist | `get_account_summary` | Phải trong registry  |
| `required_scope` | ✅       | Phạm vi quyền            | `read:transactions`   | Enum trong scopes.py |
| `is_write_tool`  | ✅       | Yêu cầu confirmation     | `true` / `false`      | Boolean              |
| `limit`          | ❌       | Số bản ghi tối đa        | `50`                  | Clamp ≤ 100          |
| `days`           | ❌       | Khoảng thời gian         | `30`                  | Clamp ≤ 365          |

## 3.3 Dòng tiền & xác nhận

### 3.3.1 Luồng write tool (Confirmation Flow)

- Bước 1: Chatbot nhận yêu cầu ghi (vd: "Giảm ngân sách mua sắm xuống 2 triệu")
- Bước 2: Tạo `pending_confirmation` trong DB với ID, summary, expiry 10 phút
- Bước 3: Trả về `requires_confirmation = True` + confirmation card lên UI
- Bước 4: Người dùng ấn "Xác nhận" → `POST /api/confirm` → thực thi thực sự
- Bước 5: Ghi audit log vào `app_chat_audit_log`

### 3.3.2 Xử lý timeout / hủy

- Confirmation hết hạn sau 10 phút → tự động vô hiệu, không thực thi
- Người dùng ấn "Hủy" → xóa pending record, không ghi dữ liệu

**Câu hỏi mở**

| Câu hỏi                                                             | Trạng thái                     |
| ------------------------------------------------------------------- | ------------------------------ |
| Có cần hiển thị lịch sử hành động đã xác nhận cho người dùng không? | TBD — có audit log, chưa có UI |
| Rate limiting `/api/chat` (mỗi call LLM tốn tiền)                   | Chưa làm — tech debt #2        |

---

# 4. Tổng quan giải pháp

## 4.1 Lộ trình sản phẩm

### 4.1.1 Các giai đoạn phát triển

| Giai đoạn          | Mô tả                                                                               | Trạng thái |
| ------------------ | ----------------------------------------------------------------------------------- | ---------- |
| Phase 1 (Hiện tại) | Chatbot tiếng Việt + dashboard cơ bản + import sao kê + guardrails + Bank Simulator | In-Review  |
| Phase 2            | Rate limiting, mobile-responsive UI, tích hợp Open Banking thực, notification       | Backlog    |
| Phase 3            | Ứng dụng mobile native, đa người dùng (gia đình), SaaS billing, phân tích nâng cao  | Tương lai  |

**Chi tiết Phase 1:**

| Khu vực       | Phase 1 (Hiện có)                                         | Giai đoạn sau                     |
| ------------- | --------------------------------------------------------- | --------------------------------- |
| AI Chatbot    | 30+ tools, multi-intent, LangGraph supervisor, guardrails | Giọng nói, multimodal             |
| Budget        | CRUD, simulate, recommend plan                            | Budget automation (auto-allocate) |
| Savings Goals | Create, simulate, archive                                 | Tích hợp savings account thực     |
| Import        | Open Banking API                                          | Open Banking API                  |
| Auth          | Session cookie local, SSO Bank Simulator                  | OAuth2 / SaaS multi-tenant        |
| Eval          | LLM-as-a-Judge + pytest regression 27 cases               | A/B testing model/prompt          |

### 4.1.2 Nguyên tắc thiết kế hệ thống

- **Allowlist tool registry:** Chatbot chỉ được gọi các tool đã khai báo trong `chat/tools.py` — không có "wildcard" call.
- **Fail-closed guardrails:** Nếu scope không được cấp phép → từ chối, không fallback mềm.
- **Write = 2 bước bắt buộc:** Không bao giờ ghi dữ liệu trực tiếp trong lần LLM call đầu tiên.
- **Deterministic trước, LLM sau:** Regex routing cho câu đơn giản → tiết kiệm latency và chi phí.
- **Audit trail:** Mọi hành động write được ghi log bất biến.

**Vòng đời tool write:**

| Trạng thái | Ý nghĩa                 | Điều kiện chuyển                      |
| ---------- | ----------------------- | ------------------------------------- |
| PENDING    | Chờ xác nhận người dùng | Sau khi LLM quyết định gọi write tool |
| CONFIRMED  | Đã thực thi             | Người dùng xác nhận trong 10 phút     |
| CANCELLED  | Đã hủy                  | Người dùng hủy hoặc timeout           |
| EXPIRED    | Hết hạn                 | Quá 10 phút chưa xác nhận             |

## 4.2 Lợi ích chính (Giá trị người dùng)

**Phase 1 — Nền tảng:**

- **Hiểu tiền ngay lập tức:** Hỏi bằng tiếng Việt tự nhiên, nhận câu trả lời chính xác từ dữ liệu thực — không cần Excel, không cần tự tính.
- **Kiểm soát ngân sách:** Cảnh báo vượt ngân sách, mô phỏng "nếu mua X thì sao" trước khi ra quyết định.
- **Mục tiêu tiết kiệm có kế hoạch:** Hệ thống tính toán cần tiết kiệm bao nhiêu mỗi tháng và đánh giá khả thi.
- **Bảo mật tuyệt đối:** Mọi hành động thay đổi dữ liệu đều cần xác nhận — chatbot không tự ý sửa bất cứ gì.
- **Điểm sức khỏe tài chính:** Hiểu tình trạng tài chính tổng thể theo thang điểm 100 với gợi ý cải thiện cụ thể.

**Giai đoạn sau — Mở rộng:**

- **Đồng bộ ngân hàng thực:** Import tự động qua Open Banking thay vì upload thủ công.
- **Thông báo chủ động:** Cảnh báo khi sắp vượt ngân sách hoặc có giao dịch bất thường.
- **Quản lý tài chính gia đình:** Chia sẻ dashboard, phân quyền giữa các thành viên.

---

# 5. User Stories & Yêu cầu

## 5.1 Must-Have (MVP — Phase 1)

### Frontend / Chat UI

| US_ID | User Story                                                                                                      | Priority | Effort |
| ----- | --------------------------------------------------------------------------------------------------------------- | -------- | ------ |
| US-01 | Là người dùng, tôi muốn gõ câu hỏi tài chính bằng tiếng Việt và nhận câu trả lời chính xác từ dữ liệu của mình. | P0       | L      |
| US-02 | Là người dùng, tôi muốn thấy confirmation card trước khi bất kỳ thay đổi nào được thực hiện để tránh lỗi nhầm.  | P0       | M      |
| US-03 | Là người dùng, tôi muốn xem dashboard tổng quan: chi tiêu, ngân sách, điểm sức khỏe tài chính.                  | P0       | M      |
| US-04 | Là người dùng, tôi muốn upload file sao kê CSV/PDF và xem giao dịch được phân loại tự động.                     | P0       | M      |
| US-05 | Là người dùng, tôi muốn tạo và theo dõi mục tiêu tiết kiệm với kế hoạch hàng tháng.                             | P1       | M      |
| US-06 | Là người dùng, tôi muốn xem lịch sử hội thoại chatbot của mình qua các phiên.                                   | P1       | S      |

### Backend / Hệ thống

| US_ID    | Nhóm         | User Story                                                                               | Priority | FE liên quan | Effort |
| -------- | ------------ | ---------------------------------------------------------------------------------------- | -------- | ------------ | ------ |
| US_BE_01 | Chatbot Core | Hệ thống định tuyến câu hỏi đến đúng tool với accuracy ≥ 90%, từ chối câu ngoài phạm vi. | P0       | US-01        | L      |
| US_BE_02 | Guardrails   | Hệ thống từ chối 100% yêu cầu tư vấn đầu tư; không lộ thông tin nhạy cảm trong response. | P0       | US-01        | M      |
| US_BE_03 | Confirmation | Mọi write tool tạo pending confirmation, không thực thi cho đến khi người dùng xác nhận. | P0       | US-02        | M      |
| US_BE_04 | Import       | Hệ thống parse và phân loại giao dịch từ CSV/PDF/OFX với tỷ lệ phân loại tự động ≥ 80%.  | P0       | US-04        | L      |
| US_BE_05 | Budget       | Hệ thống tính toán trạng thái ngân sách, mô phỏng và đề xuất kế hoạch.                   | P0       | US-03        | M      |
| US_BE_06 | Savings      | Hệ thống đánh giá khả thi mục tiêu tiết kiệm và tính số tiền cần/tháng.                  | P1       | US-05        | S      |
| US_BE_07 | Eval         | Hệ thống eval tự động (pytest + LLM judge) chạy được sau mỗi thay đổi chatbot.           | P1       | —            | M      |

---

### 5.1.1 Tiếp cận cấp cao

| US_ID    | Tóm tắt yêu cầu                                                                                    | Màn hình / API                 | Phụ thuộc                           |
| -------- | -------------------------------------------------------------------------------------------------- | ------------------------------ | ----------------------------------- |
| US-01    | Chatbot nhận text → supervisor routing → tool call → format answer → stream SSE                    | Chat Panel, `POST /api/chat`   | OpenAI/Gemini API key               |
| US-02    | Write tool tạo pending_confirmation → FE render confirmation card → `POST /api/confirm`            | Chat Panel (confirmation card) | DB `app_chat_pending_confirmations` |
| US-03    | Dashboard gọi `/api/summary`, `/api/budget`, `/api/financial-health-score`                         | Dashboard page                 | Dữ liệu giao dịch đã import         |
| US-04    | Upload file → parse → categorize → `_stream_processed_transactions` → Transactions page            | Upload page, Transactions page | `csv_parser.py` / `pdf_parser.py`   |
| US_BE_01 | LangGraph: input_guard → deterministic → fast_path / planner → executor → synthesis → output_guard | `POST /api/chat`               | LangGraph, OpenAI                   |
| US_BE_03 | Executor tạo row trong `app_chat_pending_confirmations`; `/api/confirm` thực thi và ghi audit      | `POST /api/confirm`            | DB migration 0005                   |

---

### 5.1.2 User Stories chi tiết

---

#### US-01 — AI Chatbot tiếng Việt

| Trường          | Chi tiết                                                                                                                    |
| --------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Story ID        | US-01                                                                                                                       |
| Story Name      | Chatbot hỏi đáp tài chính tiếng Việt                                                                                        |
| User Goal       | Là người dùng đang xem tài chính, tôi muốn hỏi bằng tiếng Việt tự nhiên để nhận câu trả lời dựa trên dữ liệu thực của mình. |
| Điều kiện trước | Đã đăng nhập; đã có ít nhất 1 giao dịch trong DB                                                                            |
| Điều kiện sau   | Chatbot trả lời chính xác, không lộ thông tin nhạy cảm, không bịa số liệu                                                   |

**Luồng người dùng**

_Primary Flow:_

1. Người dùng gõ câu hỏi vào Chat Panel
2. FE gửi `POST /api/chat` với `message` + `session_id`
3. Supervisor chạy input guard → routing → tool call → format
4. Stream SSE response về FE
5. FE hiển thị câu trả lời có markdown

_Alternate Flows:_

- **3a.** Câu hỏi ngoài phạm vi (đầu tư) → InvestmentAdviceGuard chặn → trả về từ chối an toàn
- **3b.** Câu hỏi đa mục đích (≥ 2 nhóm chủ đề) → planner tách thành nhiều task → synthesis gộp kết quả
- **5a.** LLM timeout → trả về thông báo lỗi an toàn, không lộ stack trace

**Acceptance Criteria**

**AC-01 — Độ chính xác tool routing**

- Intent Classification Accuracy ≥ 95%
- Tool Selection Accuracy ≥ 90%
- Câu hỏi ngoài phạm vi bị từ chối đúng 100%

**AC-02 — Chất lượng câu trả lời (LLM Judge)**

- Quality Score ≥ 4/5
- Factual Consistency = True (không bịa số liệu)
- Relevance = True
- Safe = True (không lộ API key, số tài khoản, UUID)

**AC-03 — Hiệu năng**

- Response time p95 ≤ 8 giây (bao gồm LLM call)
- Stream bắt đầu hiển thị trong ≤ 2 giây

**Dữ liệu yêu cầu**

_Input:_

| Field        | Data Type     | Required | Mô tả                              |
| ------------ | ------------- | -------- | ---------------------------------- |
| `message`    | String        | YES      | Câu hỏi tiếng Việt của người dùng  |
| `session_id` | String (UUID) | NO       | ID phiên chat; tạo mới nếu thiếu   |
| `context`    | Object        | NO       | Ngữ cảnh bổ sung (tháng, danh mục) |

_Response:_

| Field                   | Data Type | Required | Mô tả                             |
| ----------------------- | --------- | -------- | --------------------------------- |
| `message`               | String    | YES      | Câu trả lời của chatbot           |
| `requires_confirmation` | Boolean   | YES      | True nếu có write action đang chờ |
| `confirmation_id`       | String    | NO       | ID của pending confirmation       |
| `session_id`            | String    | YES      | ID phiên hiện tại                 |

**Corner Cases**

| Case                        | Mô tả                                             | Xử lý                               | UI Message                                         |
| --------------------------- | ------------------------------------------------- | ----------------------------------- | -------------------------------------------------- |
| Tư vấn đầu tư               | "Tôi nên mua coin nào?"                           | InvestmentAdviceGuard từ chối       | "Mình không thể tư vấn mua/bán tài sản đầu tư..."  |
| Yêu cầu xóa dữ liệu         | "Xóa hết dữ liệu đi"                              | OutOfScope guard từ chối            | "Tính năng này chưa được hỗ trợ qua chatbot"       |
| LLM timeout                 | Không nhận response sau 30s                       | Return error message                | "Đã xảy ra lỗi kết nối, vui lòng thử lại"          |
| Tool không tìm thấy dữ liệu | Không có giao dịch trong khoảng thời gian         | Return empty state                  | "Không tìm thấy giao dịch nào trong thời gian này" |
| Câu hỏi nhiều ý             | "Chi tiêu 6 tháng qua + kế hoạch tiết kiệm 500tr" | Planner tách 2 task → synthesis gộp | Trả lời từng phần rõ ràng                          |

---

#### US-02 — Confirmation Flow cho Write Tool

| Trường          | Chi tiết                                                                                           |
| --------------- | -------------------------------------------------------------------------------------------------- |
| Story ID        | US-02                                                                                              |
| Story Name      | Xác nhận 2 bước trước khi ghi dữ liệu                                                              |
| User Goal       | Là người dùng, tôi muốn được hỏi xác nhận trước khi chatbot thay đổi bất kỳ dữ liệu nào của tôi.   |
| Điều kiện trước | Chatbot đề xuất hành động write (update category, create rule, update budget, create savings goal) |
| Điều kiện sau   | Dữ liệu chỉ thay đổi sau khi người dùng chủ động xác nhận                                          |

**Acceptance Criteria**

**AC-01 — Confirmation bắt buộc 100%**

- Mọi write tool call phải tạo pending confirmation — không có ngoại lệ
- Confirmation Flow Accuracy = 100% (tiêu chuẩn bảo mật tuyệt đối)

**AC-02 — Expiry**

- Pending confirmation hết hạn sau 10 phút
- Sau expiry, action không thể thực thi dù người dùng ấn confirm

---

#### US-04 — Import sao kê

| Trường          | Chi tiết                                                                                   |
| --------------- | ------------------------------------------------------------------------------------------ |
| Story ID        | US-04                                                                                      |
| Story Name      | Upload và phân loại tự động giao dịch                                                      |
| User Goal       | Là người dùng, tôi muốn upload file sao kê và thấy giao dịch được phân loại đúng danh mục. |
| Điều kiện trước | Đã đăng nhập; có file CSV/PDF/OFX hợp lệ                                                   |
| Điều kiện sau   | Giao dịch hiển thị trong Transactions page với danh mục đúng                               |

**Acceptance Criteria**

**AC-01 — Hỗ trợ định dạng**

- Hỗ trợ CSV, PDF (text-based), OFX
- Parse thành công ≥ 95% file hợp lệ

**AC-02 — Tự động phân loại**

- ≥ 80% giao dịch được phân loại tự động (local categorizer + LLM fallback)
- Giao dịch chưa phân loại hiển thị rõ trạng thái "Chưa phân loại"

**AC-03 — Hiệu năng**

- File ≤ 5MB xử lý trong ≤ 30 giây
- Không block UI trong lúc xử lý (streaming progress)

---

## 5.2 Event Tracking

| Tên event                | Trigger                       | Properties                                                                |
| ------------------------ | ----------------------------- | ------------------------------------------------------------------------- |
| `chat_message_sent`      | Người dùng gửi tin nhắn       | `session_id`, `message_length`, `intent`                                  |
| `chat_response_received` | Chatbot trả về response       | `session_id`, `tools_called`, `response_time_ms`, `requires_confirmation` |
| `confirmation_shown`     | Confirmation card hiển thị    | `confirmation_id`, `tool_name`, `action_summary`                          |
| `confirmation_approved`  | Người dùng xác nhận hành động | `confirmation_id`, `tool_name`                                            |
| `confirmation_cancelled` | Người dùng hủy hành động      | `confirmation_id`, `tool_name`                                            |
| `guardrail_triggered`    | Guardrail từ chối request     | `guard_name`, `reason_code`                                               |
| `file_uploaded`          | Upload sao kê thành công      | `file_type`, `transaction_count`, `auto_categorized_count`                |
| `budget_limit_updated`   | Ngân sách được cập nhật       | `category`, `old_limit`, `new_limit`                                      |
| `savings_goal_created`   | Mục tiêu tiết kiệm mới        | `target_amount`, `months`, `monthly_required`                             |

---

# 6. Chỉ số thành công

## 6.1 Chỉ số thành công sản phẩm

| Chỉ số                         | Baseline hiện tại | Mục tiêu        |
| ------------------------------ | ----------------- | --------------- |
| Overall Pass Rate (LLM Judge)  | 84,2%             | ≥ 90%           |
| Intent Classification Accuracy | 100%              | ≥ 95% (duy trì) |
| Tool Selection Accuracy        | 94,7%             | ≥ 90% (duy trì) |
| Confirmation Flow Accuracy     | 100%              | 100% (bất biến) |
| QA Scenario Pass Rate          | 96,3% (26/27)     | ≥ 95% (duy trì) |
| File Import Success Rate       | TBD               | ≥ 95%           |
| Chat p95 Response Time         | TBD               | ≤ 8 giây        |

## 6.2 Cách đo lường

| Chỉ số                  | Công thức / Phương pháp                                                                                        |
| ----------------------- | -------------------------------------------------------------------------------------------------------------- |
| Overall Pass Rate       | `Số test case PASS / Tổng test case × 100%` — chạy `uv run spectra-chat-eval`                                  |
| Intent Accuracy         | `Số câu nhận diện đúng intent / Tổng câu test × 100%` — pytest `tests/chatbot/`                                |
| Tool Selection Accuracy | `Số lần chọn đúng tool (hoặc None đúng lúc) / Tổng scenarios × 100%`                                           |
| LLM Judge Quality       | Score 1–5 từ `eval_judge.py` dùng `gpt-4o-mini` độc lập; PASS khi score ≥ 4 và Factual/Relevance/Safe đều True |
| Confirmation Flow       | `Số write tool call có confirmation / Tổng write tool call × 100%`                                             |
| Response Time           | Đo từ `POST /api/chat` đến SSE stream end; p95 từ logs                                                         |

---

# 7. Rủi ro & Giả định

## 7.1 Giả định chính

**Về người dùng:**

- Người dùng sẵn sàng upload file sao kê thủ công (chưa có Open Banking)
- Người dùng sẽ dùng tiếng Việt không dấu hoặc có dấu — system xử lý được cả hai
- Người dùng chấp nhận latency 3–8 giây cho câu trả lời chatbot phức tạp

**Về sản phẩm:**

- GPT-4o-mini đủ chất lượng cho classification và generation ở mức chi phí chấp nhận được
- Regex routing tiếng Việt đủ tốt cho câu hỏi đơn (fast-path); LLM planner chỉ cần cho câu đa mục đích
- Bank Simulator đủ tốt để demo và test toàn luồng SSO mà không cần ngân hàng thực

**Về vận hành:**

- Supabase/PostgreSQL đáp ứng tải người dùng demo phase 1 (< 100 người dùng)
- OpenAI API không thay đổi rate limit hoặc pricing đột ngột

## 7.2 Rủi ro & Giảm thiểu

| Rủi ro                                                              | Tác động                                            | Giảm thiểu                                                                                       |
| ------------------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| LLM bịa số liệu (hallucination)                                     | Cao — người dùng đưa ra quyết định tài chính sai    | LLM Judge eval tự động; Output guard; không cho phép LLM tự suy số liệu khi không có tool output |
| Chi phí LLM tăng cao (không có rate limit)                          | Trung bình — mỗi request = 1 LLM call               | Rate limiting cho `/api/chat` là tech debt #2 — cần implement trước khi mở rộng                  |
| Prompt injection qua nội dung giao dịch                             | Cao — attacker nhúng lệnh vào description giao dịch | InputGuard `PromptInjectionGuard` chạy trên input; tool output redaction                         |
| Routing tiếng Việt brittle (regex thủ công)                         | Trung bình — câu hỏi dùng từ khác bị route sai      | Fallback LLM planner; eval regression tự động phát hiện regression                               |
| Monolith `server.py` (2900L) / `supervisor.py` (2456L) khó maintain | Thấp — chỉ ảnh hưởng developer velocity             | Tech debt #5 — refactor theo module, không urgent cho phase 1                                    |
| Layering inversion executor.py → server.py                          | Trung bình — khó test unit executor                 | Tech debt #3 — tách service layer, schedule phase 2                                              |

---

# 8. Timeline & Milestones

| Milestone            | Deliverables chính                                                                      | Mục tiêu     |
| -------------------- | --------------------------------------------------------------------------------------- | ------------ |
| Research & Design    | Kiến trúc chatbot, DB schema, guardrails spec, PRD v0.1                                 | Q4/2025      |
| Core Build — Phase 1 | Supervisor + tools + guardrails + confirmation flow + Bank Simulator SSO                | Q1/2026      |
| Hardening            | Eval harness (pytest + LLM judge), audit log, tracing LangSmith/OTel, scope enforcement | Q2/2026      |
| QA & Evaluation      | 27 QA scenarios, evaluation report, bug fixes từ judge feedback                         | Tháng 6/2026 |
| Beta nội bộ          | Demo với người dùng thực, thu thập feedback, fix known issues (Q24 routing)             | Tháng 7/2026 |
| Go-live Phase 1      | Overall Pass Rate ≥ 90%, rate limiting, production hardening                            | Q3/2026      |

---

# 9. Stakeholders & Nhóm phát triển

| Vai trò                     | Tên              | Trách nhiệm                                              |
| --------------------------- | ---------------- | -------------------------------------------------------- |
| Product Manager / Developer | Lam Pham         | Toàn bộ sản phẩm, kiến trúc, implementation              |
| AI / Chatbot Lead           | Lam Pham         | Supervisor, guardrails, eval harness, prompt engineering |
| Frontend                    | Lam Pham         | React dashboard, Chat Panel, confirmation UI             |
| QA / Evaluation             | Claude Code (AI) | Tạo test cases, chạy eval, báo cáo                       |

---

# Phụ lục

## A. Phân tích cạnh tranh

| Tính năng                   | Mint (US) | Money Lover (VN) | YNAB (US) | Spectra    |
| --------------------------- | --------- | ---------------- | --------- | ---------- |
| AI Chatbot tiếng Việt       | ❌        | ❌               | ❌        | ✅ Phase 1 |
| Import sao kê tự động       | ✅        | ✅               | ✅        | ✅ Phase 1 |
| Ngân sách & cảnh báo        | ✅        | ✅               | ✅        | ✅ Phase 1 |
| Mục tiêu tiết kiệm          | ✅        | ✅               | ✅        | ✅ Phase 1 |
| Điểm sức khỏe tài chính     | ✅        | ❌               | ❌        | ✅ Phase 1 |
| Mô phỏng kịch bản (what-if) | ❌        | ❌               | ❌        | ✅ Phase 1 |
| Confirmation flow an toàn   | N/A       | N/A              | N/A       | ✅ Phase 1 |
| Open Banking VN             | ❌        | Một số ngân hàng | ❌        | Phase 2    |
| Mobile native               | ✅        | ✅               | ✅        | Phase 3    |

## B. Tài liệu tham khảo & Phê duyệt

**Phê duyệt:**

- [ ] PRD sign-off — Lam Pham / 28/06/2026
- [ ] Technical Design sign-off — Lam Pham / 28/06/2026
- [ ] Eval Report review — 28/06/2026

**Tài liệu liên quan:**

- [PROJECT_MAP.md](PROJECT_MAP.md) — Bản đồ hệ thống, module, cheat sheet "muốn sửa X thì vào đâu"
- [chatbot-evaluation-metrics.md](chatbot-evaluation-metrics.md) — Định nghĩa chi tiết các chỉ số đánh giá chatbot
- [chatbot-qa-evaluation.md](chatbot-qa-evaluation.md) — 27 bộ câu hỏi QA với câu trả lời mẫu
- [evaluation_report.md](evaluation_report.md) — Báo cáo kết quả chạy eval gần nhất
- [spending-analysis-flow-qa.md](spending-analysis-flow-qa.md) — QA flow phân tích chi tiêu
- `supabase/migrations/` — Nguồn chân lý DB schema
- `src/spectra/chat/tools.py` — Danh sách tool chatbot + schema + quyền
- `src/spectra/chat/guardrails/` — Implementation guardrails
