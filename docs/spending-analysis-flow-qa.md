# Phân tích luồng hội thoại: Chi tiêu → Cắt giảm → Mục tiêu → So sánh → Kế hoạch

**Nguồn:** Câu hỏi thực tế từ user về trợ lý tài chính cá nhân  
**Ngày:** 2026-06-27  
**Test file:** [tests/chatbot/test_spending_analysis_flow.py](../tests/chatbot/test_spending_analysis_flow.py)  
**Kết quả:** 29 PASSED · 5 XFAILED (routing bugs đã document) · 0 FAILED

---

## Câu hỏi gốc từ user (6 flows)

```
1. Trung bình chi tiêu 6 tháng gần đây là bao nhiêu
2. Nếu cao quá thì hỏi xem để giảm % xuống thì những mục nào có thể cắt giảm
3. Liệt kê ra các mục nào chi tiêu nhiều nhất
4. Đặt mục tiêu trong 1 tgian tiết kiếm được bằng này tiền → mỗi tháng cần
   chi tiêu khoảng bao nhiêu phần trăm để đạt được mục tiêu đó
5. So sánh với những ng trong cùng độ tuổi hay cùng địa vị xã hội thì chi
   tiêu của tôi đã hợp lý chưa, so sánh và cải thiện thế nào
6. Lên kế hoạch chi tiêu cho từng mục (lời khuyên để hợp lý hơn)
```

---

## Phương pháp phân tích

Mỗi câu hỏi gốc được tách thành **4–5 test cases** nhỏ hơn, kiểm tra:
- **Intent đúng:** Tool nào được gọi?
- **Biến thể ngôn ngữ:** Cùng intent, diễn đạt khác có route đúng không?
- **Edge cases:** Income có/không trong câu, scope ngắn/dài hạn.
- **Gaps:** Tính năng nào hệ thống chưa có?

---

## Block A — "Trung bình chi tiêu 6 tháng gần đây là bao nhiêu?"

### Phân tích thiết kế

| Câu hỏi con | Tool kỳ vọng | Vấn đề |
|-------------|-------------|--------|
| "6 tháng gần đây" | `get_account_summary` | ⚠️ "6 tháng" ≠ scope có sẵn (cycle/90d/ytd) |
| "Nửa năm qua" | `get_account_summary` | Biến thể ngôn ngữ |
| "Từ đầu năm đến nay" | `get_account_summary(scope=ytd)` | Scope mapping đúng |
| Trung bình + tháng nào cao nhất | `get_account_summary` | 2 thông tin từ 1 call |

**Vấn đề scope "6 tháng":** Hệ thống có 3 scope cố định: `cycle` (tháng hiện tại), `90d` (3 tháng), `ytd` (từ đầu năm). Để lấy đúng 6 tháng, supervisor phải dùng `date_from`/`date_to`. Hiện tại supervisor thường fallback về `ytd` — chấp nhận được nhưng không chính xác khi gần cuối năm.

### Test cases & kết quả

| Test | Câu hỏi | Kết quả | Tool gọi |
|------|---------|---------|----------|
| A1 | "Trung bình chi tiêu 6 tháng gần đây là bao nhiêu?" | ✅ PASS | `get_account_summary` |
| A2 | "Nửa năm qua tôi tiêu bao nhiêu tiền?" | ✅ PASS | `get_account_summary` |
| A3 | "Từ đầu năm đến nay tôi chi bao nhiêu?" | ✅ PASS | `get_account_summary(scope=ytd)` |
| A4 | "Chi tiêu trung bình 6 tháng và tháng nào cao nhất?" | ✅ PASS | `get_account_summary` |
| A5 | "Tổng chi tiêu trong 6 tháng gần nhất" (kiểm tra date_range) | ✅ PASS | `get_account_summary` |

**Câu trả lời mẫu (A1):**
```
6 tháng gần đây (01/01–06/2026):
  Tổng chi tiêu:    51.000.000 VND
  Trung bình/tháng:  8.500.000 VND

Tháng chi nhiều nhất: [dữ liệu từ account summary]

Danh mục chính:
• Ăn uống:    19.200.000 VND  (37,6%)
• Mua sắm:   14.400.000 VND  (28,2%)
• Di chuyển:  6.600.000 VND  (12,9%)
```

---

## Block B — "Nếu cao quá thì những mục nào có thể cắt giảm?"

### Phân tích thiết kế

> **Lưu ý:** Đây là câu hỏi **conditional follow-up** — user đã thấy số liệu cao và muốn giải pháp.  
> Không phải "if" branch trong code — đây là turn kế tiếp trong hội thoại.

**Tools phù hợp:**
- `get_budget_status` → xem danh mục nào đang over/at-risk
- `explain_budget_overrun` → giải thích nguyên nhân vượt ngân sách
- `simulate_budget_adjustment` → mô phỏng kết quả nếu cắt giảm X%

**Phân biệt 2 loại câu hỏi cắt giảm:**
1. *"Cắt ở đâu?"* → `get_budget_status` + `explain_budget_overrun`
2. *"Giảm X% thì cắt thế nào?"* → `simulate_budget_adjustment` (routing bug hiện tại)

### Test cases & kết quả

| Test | Câu hỏi | Kết quả | Tool gọi | Bug |
|------|---------|---------|----------|-----|
| B1 | "Chi tiêu cao quá, cần cắt giảm ở đâu?" | ✅ PASS | `get_account_summary` | |
| **B2** | "Muốn giảm 20%, cần cắt ở đâu?" | ⚠️ XFAIL | `set()` | Số % không trigger simulate |
| B3 | "Cần tiết kiệm thêm 2tr/tháng, cắt gì?" | ✅ PASS | `get_account_summary` | |
| B4 | "Mục nào không cần thiết?" | ✅ PASS | `get_budget_status` | |
| B5 | "Đang vượt ngân sách, phải làm gì?" | ✅ PASS | `explain_budget_overrun` | |

**Bug B2 — Routing không nhận pattern số %:**
```
Input:  "Tôi muốn giảm chi tiêu xuống 20%, cần cắt ở những mục nào?"
Thực tế: tools = set()  ← chatbot trả lời trực tiếp không gọi tool
Kỳ vọng: simulate_budget_adjustment hoặc get_budget_status
Fix:    Thêm pattern "giảm X%" / "cắt giảm phần trăm" → simulate_budget_adjustment
```

**Câu trả lời mẫu (B1):**
```
Để cắt giảm chi tiêu, bạn nên xem xét:

🔴 Vượt ngân sách (cần cắt):
  • Ăn uống:  3.200.000 VND (vượt 200.000) — giảm đặt đồ ăn online
  • Mua sắm:  2.400.000 VND (vượt 400.000) — đặt ngân sách tuần

💡 Có thể tối ưu:
  • Giải trí:  800.000 VND (sát giới hạn) — tìm hoạt động miễn phí

→ Nếu cắt Ăn uống -700k + Mua sắm -700k + Giải trí -300k:
  Tiết kiệm thêm: ~1.700.000 VND/tháng
```

---

## Block C — "Liệt kê các mục chi tiêu nhiều nhất"

### Phân tích thiết kế

Câu hỏi này thường là **follow-up sau Block A** — data đã có trong `get_account_summary`.  
Không cần tool call riêng nếu đã có context. Các biến thể chính:

| Cách diễn đạt | Mapping |
|---------------|---------|
| "Liệt kê mục chi nhiều nhất" | `get_account_summary.top_categories` |
| "Top 3 danh mục" | `get_account_summary.top_categories[:3]` |
| "Mục nào ăn tiền nhất" | Informal — cùng intent |
| "Tỷ lệ % từng danh mục" | Cần tính toán: amount/total_spent |

### Test cases & kết quả

| Test | Câu hỏi | Kết quả |
|------|---------|---------|
| C1 | "Liệt kê các mục chi tiêu nhiều nhất" | ✅ PASS |
| C2 | "Top 3 danh mục 6 tháng qua" | ✅ PASS |
| C3 | "Mục nào đang ăn tiền nhất?" | ✅ PASS |
| C4 | "Mỗi danh mục chiếm bao nhiêu % tổng chi?" | ✅ PASS |

**Câu trả lời mẫu (C1 — user mẫu):**
```
Top danh mục chi tiêu (6 tháng, trung bình/tháng):

1. 🍜 Ăn uống       3.200.000 VND  (37,6%)  ⚠️ vượt ngân sách
2. 🛒 Mua sắm       2.400.000 VND  (28,2%)  ⚠️ vượt ngân sách
3. 🚗 Di chuyển     1.100.000 VND  (12,9%)  ✅
4. 🎬 Giải trí        800.000 VND   (9,4%)  ✅
5. 🏠 Nhà ở           500.000 VND   (5,9%)  ✅
```

---

## Block D — "Đặt mục tiêu tiết kiệm → cần bao nhiêu % mỗi tháng?"

### Phân tích thiết kế

Đây là câu hỏi phức tạp về **công thức**:

```
Cần tiết kiệm/tháng = plan_savings_goal.monthly_required_amount
% cần tiết kiệm     = monthly_required / monthly_income × 100
% còn để chi tiêu  = 100% - % cần tiết kiệm

Tool flow:
  plan_savings_goal(target, date) → monthly_required_amount
  get_account_summary()           → monthly_income (nếu user không nói)
  → Supervisor tính: pct = monthly_required / income × 100
```

**Vấn đề thiết kế quan trọng:**
- User hỏi *"bao nhiêu %"* — không phải số tuyệt đối.
- `plan_savings_goal` trả về số tuyệt đối.
- Supervisor phải tự tính % từ income.
- Nếu user không cung cấp income → cần gọi `get_account_summary` trước.

### Test cases & kết quả

| Test | Câu hỏi | Kết quả | Tool gọi | Bug |
|------|---------|---------|----------|-----|
| D1 | "Lương 15tr, tiết kiệm 100tr trong 2 năm, cần % nào?" | ✅ PASS | `plan_savings_goal` | |
| D2 | "Để dành 50tr trong 1 năm, cần bao nhiêu/tháng?" | ✅ PASS | `plan_savings_goal` | |
| D3 | "Đến Tết để dành 20tr, mỗi tháng chi tối đa bao nhiêu?" | ✅ PASS | `plan_savings_goal` | |
| **D4** | "500tr trong 5 năm, cần bao nhiêu % thu nhập?" | ⚠️ XFAIL | `set()` | "% thu nhập" làm bối rối supervisor |
| **D5** | "Tiết kiệm 30% thu nhập, lên kế hoạch ngân sách" | ⚠️ XFAIL | `get_current_user` | % input → sai routing |

**Bug D4, D5 — Routing không xử lý % input:**
```
D4: Input "bao nhiêu phần trăm thu nhập" → tools = set() (không gọi tool)
D5: Input "tiết kiệm 30% thu nhập"       → get_current_user (sai hoàn toàn)

Fix chung: Pattern "X% thu nhập" + ("tiết kiệm" hoặc "lên kế hoạch") →
  recommend_budget_plan(target_savings_amount = income × X%)
```

**Câu trả lời mẫu (D1):**
```
Kế hoạch tiết kiệm 100.000.000 VND trong 2 năm:

  Cần tiết kiệm/tháng:  4.166.667 VND
  % thu nhập (15tr):    27,8%
  Còn lại để chi tiêu: 72,2% = 10.833.333 VND/tháng

  Khả thi? ✅ Thặng dư hiện tại: 6.500.000 > 4.166.667 VND

Kế hoạch ngân sách tháng (còn lại 10,8tr):
  Nhà ở:     3.500.000  (32%)
  Ăn uống:   2.500.000  (23%)
  Di chuyển: 1.200.000  (11%)
  Mua sắm:   1.500.000  (14%)
  Giải trí:    700.000   (6%)
  Dự phòng:  1.433.333  (13%)
```

---

## Block E — "So sánh với người cùng độ tuổi / địa vị" ⚠️ FEATURE GAP

### Phân tích thiết kế

> **ĐÂY LÀ GAP TÍNH NĂNG — Hệ thống không có peer comparison data.**

**Không tồn tại tool nào cho:**
- Benchmark theo độ tuổi (18-25, 25-35, 35-45...)
- Benchmark theo thu nhập tier (< 10tr, 10-20tr, > 20tr)
- Benchmark theo địa vị (nhân viên, quản lý, tự kinh doanh...)
- So sánh với người dùng khác trong database

**Routing bug hiện tại:** Từ khóa "so sánh" trigger `compare_period_spending` (so sánh kỳ trước), hoàn toàn sai intent.

**Hành vi đúng cần implement:**
1. Từ chối gracefully: "Spectra chưa có dữ liệu benchmark người dùng cùng độ tuổi"
2. Đề xuất alternative: Dùng `get_financial_health_score` + quy tắc 50-30-20

### Test cases & kết quả

| Test | Câu hỏi | Kết quả | Bug |
|------|---------|---------|-----|
| **E1** | "So sánh với người cùng độ tuổi 25-30" | ⚠️ XFAIL | "so sánh" → compare_period_spending |
| **E2** | "Người lương 15tr thường chi bao nhiêu cho ăn uống?" | ⚠️ XFAIL | Benchmark question → compare_period_spending |
| E3 | "Chi tiêu của tôi có hợp lý không?" | ✅ PASS | Hỏi chung → trả lời được |
| E4 | "Tôi có đang tiết kiệm đủ không?" | ✅ PASS | Hỏi chung → trả lời được |

**Bugs E1, E2 — Cùng root cause:**
```
"so sánh" keyword → supervisor route đến compare_period_spending
Response: "So voi ky truoc, ky hien tai chi bang 0 VND" ← hoàn toàn sai

Fix: Intent detection cho "người khác" / "cùng độ tuổi" / "người cùng" →
  Không route đến compare_period_spending.
  Thay vào đó: graceful decline + gợi ý financial health score.
```

**Roadmap tính năng peer comparison (tương lai):**
```
Option A: Hardcode benchmark theo quy tắc tài chính phổ biến
  - Ăn uống: 15-25% income (WHO/finance guideline)
  - Nhà ở: ≤ 30% income (rule of thumb)
  - Tiết kiệm: ≥ 20% income (50-30-20 rule)

Option B: Anonymous aggregate từ user database (privacy-preserving)
  - Trung bình chi Ăn uống của user thu nhập 10-15tr/tháng ở VN
  - Cần ít nhất 1000+ users để có statistical significance

Option C: Integrate external VN financial benchmark data
  - GSO (Tổng cục Thống kê) hoặc StoxPlus data
```

---

## Block F — "Lên kế hoạch chi tiêu từng mục với lời khuyên"

### Phân tích thiết kế

**Tool chính:** `recommend_budget_plan`  
**Input:** `monthly_income` + `target_savings_amount`  
**Output:** Danh sách giới hạn từng danh mục  

Phần *"lời khuyên"* là LLM synthesis — không deterministic, test chỉ kiểm tra tool routing.

**Biến thể câu hỏi:**

| Dạng | Tool flow |
|------|-----------|
| "Lên kế hoạch ngân sách" | `recommend_budget_plan` |
| "Nên chi bao nhiêu cho X?" | `get_budget_status` hoặc `recommend_budget_plan` |
| "Lời khuyên cắt giảm X" | `explain_budget_overrun` (bug hiện tại → `get_recurring_transactions`) |
| "Kế hoạch đầy đủ kèm lời khuyên" | `recommend_budget_plan` + `get_account_summary` |

### Test cases & kết quả

| Test | Câu hỏi | Kết quả | Tool gọi | Bug |
|------|---------|---------|----------|-----|
| F1 | "Lên kế hoạch ngân sách cho tôi" | ✅ PASS | `recommend_budget_plan` | |
| F2 | "Lương 18tr, tiết kiệm 20%, lên kế hoạch" | ✅ PASS | `recommend_budget_plan` | |
| F3 | "Nên chi bao nhiêu cho ăn uống?" | ✅ PASS | `get_budget_status` | |
| **F4** | "Lời khuyên cắt giảm ăn uống" | ⚠️ XFAIL | `get_recurring_transactions` | Sai intent |
| F5 | "Kế hoạch đầy đủ kèm lời khuyên từng mục" | ✅ PASS | `recommend_budget_plan` | |

**Bug F4 — "Lời khuyên" + category name → sai tool:**
```
Input:  "Cho tôi lời khuyên để cắt giảm chi phí ăn uống hàng tháng"
Thực tế: get_recurring_transactions (tìm recurring food payments)
Kỳ vọng: explain_budget_overrun(category="ăn uống") hoặc recommend_budget_plan

Fix: Pattern "lời khuyên" + "cắt giảm" + [tên danh mục] →
  explain_budget_overrun(category=extracted_category)
```

**Câu trả lời mẫu (F2):**
```
Kế hoạch ngân sách tháng — Thu nhập 18.000.000 VND, tiết kiệm 20% (3.600.000):

Danh mục        Giới hạn        %      Lời khuyên
────────────────────────────────────────────────────────────────
Tiết kiệm       3.600.000      20%    Rút trước khi chi tiêu ✨
Nhà ở           4.000.000      22%    Chi phí cố định — ưu tiên ổn định
Ăn uống         3.000.000      17%    Giảm Grab Food 2-3 lần/tuần (-300k)
Di chuyển       1.500.000       8%    Cân nhắc combo tháng Grab
Mua sắm         2.000.000      11%    Đặt ngân sách tuần (500k/tuần)
Giải trí          800.000       4%    Tìm hoạt động ngoài trời miễn phí
Dự phòng        3.100.000      17%    Xây dựng quỹ khẩn cấp

Tổng: 18.000.000 VND  |  Còn lại: 0 VND
```

---

## Block G — Full Conversation Flow (multi-turn simulation)

Kiểm tra toàn bộ 6 turns như người dùng đề xuất, mỗi turn độc lập:

| Turn | Câu hỏi | Kết quả | Tool gọi |
|------|---------|---------|----------|
| G1 | Trung bình chi tiêu 6 tháng | ✅ PASS | `get_account_summary` |
| G2 | Cao quá, cắt gì? | ✅ PASS | `get_account_summary` |
| G3 | Liệt kê mục chi nhiều nhất | ✅ PASS | `get_account_summary` |
| G4 | Tiết kiệm 100tr trong 2 năm → % mỗi tháng | ✅ PASS | `plan_savings_goal` |
| G5 | So sánh với người cùng độ tuổi | ✅ PASS (loose assertion) | varies |
| G6 | Kế hoạch ngân sách kèm lời khuyên | ✅ PASS | `recommend_budget_plan` |

---

## Tổng hợp Routing Bugs phát hiện

| Bug ID | Câu hỏi pattern | Tool thực tế | Tool kỳ vọng | Priority |
|--------|-----------------|-------------|-------------|----------|
| B2 | "giảm X%" | `set()` | `simulate_budget_adjustment` | Medium |
| D4 | "bao nhiêu % thu nhập" + goal | `set()` | `plan_savings_goal` | Medium |
| D5 | "tiết kiệm X% thu nhập" + kế hoạch | `get_current_user` | `recommend_budget_plan` | High |
| E1 | "so sánh với người cùng [X]" | `compare_period_spending` | graceful decline | High |
| E2 | "người [X] thường chi bao nhiêu" | `compare_period_spending` | graceful decline | Medium |
| F4 | "lời khuyên cắt giảm [category]" | `get_recurring_transactions` | `explain_budget_overrun` | Medium |

### Nhóm fix theo root cause

**Root cause 1: Keyword "so sánh" → luôn route đến compare_period_spending**  
Ảnh hưởng: E1, E2  
Fix: Thêm pre-check — nếu có "người khác / cùng tuổi / cùng địa vị" thì không route đến compare_period_spending.

**Root cause 2: Số học % trong câu hỏi làm supervisor bối rối**  
Ảnh hưởng: B2, D4, D5  
Fix: Parser pattern số học — "X%" + ("giảm / tiết kiệm / lên kế hoạch") → map đến tool đúng.

**Root cause 3: "lời khuyên" + tên danh mục → tìm recurring**  
Ảnh hưởng: F4  
Fix: "lời khuyên cắt giảm [category]" → `explain_budget_overrun(category=...)` trước.

---

## Feature Gap: Peer Comparison

**Không có trong hệ thống. Cần thiết kế nếu muốn implement:**

```
Hướng implement ưu tiên nhất (Option A — không cần user data):

Hardcode Vietnamese financial benchmarks theo income tier:

  Income < 8tr/tháng:
    Ăn uống: 25-35%, Nhà ở: 25-35%, Tiết kiệm ≥ 10%

  Income 8-15tr/tháng:
    Ăn uống: 20-25%, Nhà ở: 20-30%, Tiết kiệm ≥ 15%

  Income 15-25tr/tháng:
    Ăn uống: 15-20%, Nhà ở: 20-25%, Tiết kiệm ≥ 20%

  Income > 25tr/tháng:
    Ăn uống: 10-15%, Nhà ở: 15-20%, Tiết kiệm ≥ 25%

Tool mới cần tạo: compare_with_benchmark(income_tier, category)
```

---

*File được tạo tự động từ kết quả phân tích câu hỏi và chạy [tests/chatbot/test_spending_analysis_flow.py](../tests/chatbot/test_spending_analysis_flow.py)*
