-- ============================================================================
-- Bank Simulator Database Schema
-- Purpose: Tạo dữ liệu giả lập chất lượng cao cho AI Financial Advisor
-- Author: Senior Software Engineer & Data Architect
-- ============================================================================

-- Extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Table: bank_accounts
-- Description: Lưu trữ thông tin tài khoản ngân hàng của người dùng
-- ============================================================================
CREATE TABLE IF NOT EXISTS bank_accounts (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id           UUID NOT NULL,
    account_number    VARCHAR(20) NOT NULL UNIQUE,
    bank_name         VARCHAR(100) NOT NULL,
    balance           NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    account_type      VARCHAR(20) NOT NULL DEFAULT 'checking', -- checking, savings
    currency          VARCHAR(3) NOT NULL DEFAULT 'VND',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT chk_balance_positive CHECK (balance >= 0),
    CONSTRAINT chk_account_type CHECK (account_type IN ('checking', 'savings'))
);

-- ============================================================================
-- Table: bank_transactions
-- Description: Lưu trữ tất cả giao dịch ngân hàng
-- ============================================================================
CREATE TABLE IF NOT EXISTS bank_transactions (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id               UUID NOT NULL,
    account_id            UUID NOT NULL REFERENCES bank_accounts(id) ON DELETE CASCADE,
    transaction_type      VARCHAR(20) NOT NULL, -- debit, credit
    amount                NUMERIC(15, 2) NOT NULL,
    merchant              VARCHAR(255) NOT NULL,
    merchant_category     VARCHAR(100) NOT NULL,
    category              VARCHAR(100) NOT NULL,
    description           TEXT,
    balance_after         NUMERIC(15, 2) NOT NULL,
    is_anomaly            BOOLEAN NOT NULL DEFAULT FALSE,
    anomaly_reason        TEXT,
    location              VARCHAR(255),
    payment_method        VARCHAR(50), -- card, transfer, cash, online
    reference_number      VARCHAR(100) UNIQUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT chk_amount_positive CHECK (amount > 0),
    CONSTRAINT chk_transaction_type CHECK (transaction_type IN ('debit', 'credit')),
    CONSTRAINT fk_account FOREIGN KEY (account_id) REFERENCES bank_accounts(id)
);

-- ============================================================================
-- Table: user_personas
-- Description: Lưu trữ thông tin persona của người dùng (Student, Office Worker, High-Net-Worth)
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_personas (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id           UUID NOT NULL UNIQUE,
    persona_type      VARCHAR(50) NOT NULL,
    monthly_income    NUMERIC(15, 2) NOT NULL,
    spending_pattern  JSONB, -- Lưu trữ pattern chi tiêu dạng JSON
    risk_profile      VARCHAR(20), -- low, medium, high
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT chk_persona_type CHECK (persona_type IN ('Student', 'Office Worker', 'High-Net-Worth'))
);

-- ============================================================================
-- Table: transaction_patterns
-- Description: Lưu trữ các pattern giao dịch để phát hiện anomaly
-- ============================================================================
CREATE TABLE IF NOT EXISTS transaction_patterns (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id           UUID NOT NULL,
    category          VARCHAR(100) NOT NULL,
    avg_amount        NUMERIC(15, 2) NOT NULL,
    std_deviation     NUMERIC(15, 2) NOT NULL,
    frequency_per_month INTEGER NOT NULL,
    typical_merchants JSONB, -- Danh sách merchant thường xuyên
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Indexes for Performance Optimization
-- ============================================================================

-- Indexes cho bank_accounts
CREATE INDEX IF NOT EXISTS idx_bank_accounts_user_id ON bank_accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_bank_accounts_account_number ON bank_accounts(account_number);

-- Indexes cho bank_transactions (Critical for query performance)
CREATE INDEX IF NOT EXISTS idx_bank_transactions_user_id ON bank_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_bank_transactions_created_at ON bank_transactions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bank_transactions_user_created ON bank_transactions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bank_transactions_category ON bank_transactions(category);
CREATE INDEX IF NOT EXISTS idx_bank_transactions_is_anomaly ON bank_transactions(is_anomaly) WHERE is_anomaly = TRUE;
CREATE INDEX IF NOT EXISTS idx_bank_transactions_merchant ON bank_transactions(merchant);
CREATE INDEX IF NOT EXISTS idx_bank_transactions_account_id ON bank_transactions(account_id);

-- Composite index cho queries phức tạp
CREATE INDEX IF NOT EXISTS idx_bank_transactions_user_category_date 
    ON bank_transactions(user_id, category, created_at DESC);

-- Indexes cho user_personas
CREATE INDEX IF NOT EXISTS idx_user_personas_user_id ON user_personas(user_id);
CREATE INDEX IF NOT EXISTS idx_user_personas_persona_type ON user_personas(persona_type);

-- Indexes cho transaction_patterns
CREATE INDEX IF NOT EXISTS idx_transaction_patterns_user_id ON transaction_patterns(user_id);
CREATE INDEX IF NOT EXISTS idx_transaction_patterns_category ON transaction_patterns(category);

-- ============================================================================
-- Views for Analytics
-- ============================================================================

-- View: Tổng quan chi tiêu theo user và category
CREATE OR REPLACE VIEW v_spending_summary AS
SELECT 
    user_id,
    category,
    COUNT(*) as transaction_count,
    SUM(amount) as total_amount,
    AVG(amount) as avg_amount,
    MIN(amount) as min_amount,
    MAX(amount) as max_amount,
    DATE_TRUNC('month', created_at) as month
FROM bank_transactions
WHERE transaction_type = 'debit'
GROUP BY user_id, category, DATE_TRUNC('month', created_at);

-- View: Anomaly transactions summary
CREATE OR REPLACE VIEW v_anomaly_summary AS
SELECT 
    user_id,
    COUNT(*) as anomaly_count,
    SUM(amount) as total_anomaly_amount,
    array_agg(DISTINCT anomaly_reason) as anomaly_reasons,
    DATE_TRUNC('day', created_at) as date
FROM bank_transactions
WHERE is_anomaly = TRUE
GROUP BY user_id, DATE_TRUNC('day', created_at);

-- View: User spending by persona
CREATE OR REPLACE VIEW v_persona_spending AS
SELECT 
    up.persona_type,
    up.user_id,
    COUNT(bt.id) as transaction_count,
    SUM(bt.amount) as total_spending,
    AVG(bt.amount) as avg_transaction,
    COUNT(CASE WHEN bt.is_anomaly THEN 1 END) as anomaly_count
FROM user_personas up
LEFT JOIN bank_transactions bt ON up.user_id = bt.user_id
WHERE bt.transaction_type = 'debit'
GROUP BY up.persona_type, up.user_id;

-- ============================================================================
-- Functions for Data Integrity
-- ============================================================================

-- Function: Update account balance after transaction
CREATE OR REPLACE FUNCTION update_account_balance()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.transaction_type = 'debit' THEN
        UPDATE bank_accounts 
        SET balance = balance - NEW.amount,
            updated_at = NOW()
        WHERE id = NEW.account_id;
    ELSE
        UPDATE bank_accounts 
        SET balance = balance + NEW.amount,
            updated_at = NOW()
        WHERE id = NEW.account_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: Auto update balance
CREATE TRIGGER trg_update_account_balance
    AFTER INSERT ON bank_transactions
    FOR EACH ROW
    EXECUTE FUNCTION update_account_balance();

-- Function: Validate transaction amount against balance
CREATE OR REPLACE FUNCTION validate_transaction_balance()
RETURNS TRIGGER AS $$
DECLARE
    current_balance NUMERIC(15, 2);
BEGIN
    IF NEW.transaction_type = 'debit' THEN
        SELECT balance INTO current_balance
        FROM bank_accounts
        WHERE id = NEW.account_id;
        
        IF current_balance < NEW.amount THEN
            RAISE EXCEPTION 'Insufficient balance. Current: %, Required: %', current_balance, NEW.amount;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: Validate before insert
CREATE TRIGGER trg_validate_transaction_balance
    BEFORE INSERT ON bank_transactions
    FOR EACH ROW
    EXECUTE FUNCTION validate_transaction_balance();

-- ============================================================================
-- Utility Functions
-- ============================================================================

-- Function: Get user spending summary
CREATE OR REPLACE FUNCTION get_user_spending_summary(p_user_id UUID, p_months INTEGER DEFAULT 3)
RETURNS TABLE (
    category VARCHAR,
    total_amount NUMERIC,
    transaction_count BIGINT,
    avg_amount NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        bt.category,
        SUM(bt.amount) as total_amount,
        COUNT(*) as transaction_count,
        AVG(bt.amount) as avg_amount
    FROM bank_transactions bt
    WHERE bt.user_id = p_user_id
        AND bt.transaction_type = 'debit'
        AND bt.created_at >= NOW() - (p_months || ' months')::INTERVAL
    GROUP BY bt.category
    ORDER BY total_amount DESC;
END;
$$ LANGUAGE plpgsql;

-- Function: Detect anomalies based on user patterns
CREATE OR REPLACE FUNCTION detect_transaction_anomaly(
    p_user_id UUID,
    p_category VARCHAR,
    p_amount NUMERIC
)
RETURNS BOOLEAN AS $$
DECLARE
    v_avg_amount NUMERIC;
    v_std_dev NUMERIC;
    v_threshold NUMERIC;
BEGIN
    -- Get average and standard deviation for this user and category
    SELECT avg_amount, std_deviation
    INTO v_avg_amount, v_std_dev
    FROM transaction_patterns
    WHERE user_id = p_user_id AND category = p_category;
    
    -- If no pattern exists, not an anomaly
    IF v_avg_amount IS NULL THEN
        RETURN FALSE;
    END IF;
    
    -- Anomaly if amount > avg + 2*std_dev (2 sigma rule)
    v_threshold := v_avg_amount + (2 * v_std_dev);
    
    RETURN p_amount > v_threshold;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE bank_accounts IS 'Lưu trữ thông tin tài khoản ngân hàng của người dùng';
COMMENT ON TABLE bank_transactions IS 'Lưu trữ tất cả giao dịch ngân hàng với đầy đủ metadata';
COMMENT ON TABLE user_personas IS 'Phân loại người dùng theo persona để tạo dữ liệu realistic';
COMMENT ON TABLE transaction_patterns IS 'Pattern giao dịch để phát hiện anomaly';

COMMENT ON COLUMN bank_transactions.is_anomaly IS 'Flag đánh dấu giao dịch bất thường (5% của tổng số)';
COMMENT ON COLUMN bank_transactions.anomaly_reason IS 'Lý do giao dịch được đánh dấu là anomaly';
COMMENT ON COLUMN bank_transactions.balance_after IS 'Số dư sau khi thực hiện giao dịch';

-- ============================================================================
-- Grant Permissions (Optional - adjust based on your setup)
-- ============================================================================

-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO your_user;

-- ============================================================================
-- End of Schema
-- ============================================================================
