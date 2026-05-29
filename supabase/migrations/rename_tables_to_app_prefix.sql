-- ============================================================================
-- Script đổi tên bảng sang định dạng có tiền tố 'app_'
-- Database: PostgreSQL (Supabase)
-- Ngày tạo: 2026-05-29
-- ============================================================================

-- Bắt đầu transaction để đảm bảo tính toàn vẹn dữ liệu
BEGIN;

-- ============================================================================
-- BƯỚC 1: ĐỔI TÊN CÁC BẢNG
-- ============================================================================

-- Đổi tên bảng seen_transactions
ALTER TABLE IF EXISTS "public"."seen_transactions" 
RENAME TO "app_seen_transactions";

-- Đổi tên bảng tx_history
ALTER TABLE IF EXISTS "public"."tx_history" 
RENAME TO "app_tx_history";

-- Đổi tên bảng user_overrides
ALTER TABLE IF EXISTS "public"."user_overrides" 
RENAME TO "app_user_overrides";

-- Đổi tên bảng merchant_categories
ALTER TABLE IF EXISTS "public"."merchant_categories" 
RENAME TO "app_merchant_categories";

-- Đổi tên bảng budget_limits
ALTER TABLE IF EXISTS "public"."budget_limits" 
RENAME TO "app_budget_limits";

-- Đổi tên bảng app_settings (đã có tiền tố app_ rồi, bỏ qua)
-- Bảng này đã có tên đúng format

-- Đổi tên bảng category_rules
ALTER TABLE IF EXISTS "public"."category_rules" 
RENAME TO "app_category_rules";

-- Đổi tên bảng learning_feedback
ALTER TABLE IF EXISTS "public"."learning_feedback" 
RENAME TO "app_learning_feedback";

-- ============================================================================
-- BƯỚC 2: ĐỔI TÊN CÁC INDEX (nếu có)
-- ============================================================================

-- Đổi tên index của bảng tx_history (giờ là app_tx_history)
ALTER INDEX IF EXISTS "public"."idx_tx_history_date" 
RENAME TO "idx_app_tx_history_date";

ALTER INDEX IF EXISTS "public"."idx_tx_history_category" 
RENAME TO "idx_app_tx_history_category";

ALTER INDEX IF EXISTS "public"."idx_tx_history_clean_name" 
RENAME TO "idx_app_tx_history_clean_name";

-- ============================================================================
-- BƯỚC 3: ĐỔI TÊN CÁC CONSTRAINT (Primary Keys, Unique Constraints)
-- ============================================================================

-- PostgreSQL tự động đổi tên các constraint khi đổi tên bảng,
-- nhưng để đảm bảo tính nhất quán, ta có thể đổi tên thủ công:

-- Primary key của app_seen_transactions
ALTER TABLE IF EXISTS "public"."app_seen_transactions" 
RENAME CONSTRAINT "seen_transactions_pkey" TO "app_seen_transactions_pkey";

-- Primary key của app_tx_history
ALTER TABLE IF EXISTS "public"."app_tx_history" 
RENAME CONSTRAINT "tx_history_pkey" TO "app_tx_history_pkey";

-- Primary key của app_user_overrides
ALTER TABLE IF EXISTS "public"."app_user_overrides" 
RENAME CONSTRAINT "user_overrides_pkey" TO "app_user_overrides_pkey";

-- Primary key của app_merchant_categories
ALTER TABLE IF EXISTS "public"."app_merchant_categories" 
RENAME CONSTRAINT "merchant_categories_pkey" TO "app_merchant_categories_pkey";

-- Primary key của app_budget_limits
ALTER TABLE IF EXISTS "public"."app_budget_limits" 
RENAME CONSTRAINT "budget_limits_pkey" TO "app_budget_limits_pkey";

-- Primary key của app_category_rules
ALTER TABLE IF EXISTS "public"."app_category_rules" 
RENAME CONSTRAINT "category_rules_pkey" TO "app_category_rules_pkey";

-- Primary key của app_learning_feedback
ALTER TABLE IF EXISTS "public"."app_learning_feedback" 
RENAME CONSTRAINT "learning_feedback_pkey" TO "app_learning_feedback_pkey";

-- ============================================================================
-- BƯỚC 4: KIỂM TRA KẾT QUẢ
-- ============================================================================

-- Liệt kê tất cả các bảng có tiền tố 'app_' để xác nhận
SELECT 
    schemaname,
    tablename
FROM pg_tables
WHERE schemaname = 'public' 
    AND tablename LIKE 'app_%'
ORDER BY tablename;

-- ============================================================================
-- KẾT THÚC TRANSACTION
-- ============================================================================

-- Nếu mọi thứ OK, commit transaction
COMMIT;

-- Nếu có lỗi, bạn có thể rollback bằng lệnh:
-- ROLLBACK;

-- ============================================================================
-- GHI CHÚ QUAN TRỌNG
-- ============================================================================

/*
DANH SÁCH CÁC BẢNG ĐÃ ĐỔI TÊN:
1. seen_transactions        → app_seen_transactions
2. tx_history              → app_tx_history
3. user_overrides          → app_user_overrides
4. merchant_categories     → app_merchant_categories
5. budget_limits           → app_budget_limits
6. app_settings            → app_settings (giữ nguyên)
7. category_rules          → app_category_rules
8. learning_feedback       → app_learning_feedback

KIỂM TRA KHÓA NGOẠI:
- Các bảng trong database này KHÔNG có foreign key constraints
- Không cần cập nhật thêm ràng buộc khóa ngoại

SAU KHI CHẠY SCRIPT:
1. Cập nhật lại code ứng dụng để sử dụng tên bảng mới
2. Cập nhật file migration/schema nếu có
3. Kiểm tra Row Level Security (RLS) policies vẫn hoạt động đúng
4. Kiểm tra các stored procedures/functions nếu có tham chiếu đến tên bảng cũ

CÁCH SỬ DỤNG:
1. Copy toàn bộ script này
2. Mở SQL Editor trong Supabase
3. Paste và chạy script
4. Kiểm tra kết quả bằng query SELECT cuối cùng
5. Nếu có lỗi, chạy ROLLBACK; để hoàn tác
*/
