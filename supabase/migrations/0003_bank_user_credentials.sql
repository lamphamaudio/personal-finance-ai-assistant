-- Demo credentials for Bank Simulator username/password login.
-- Passwords are stored as PBKDF2-SHA256 hashes; plaintext demo passwords
-- are seeded by the application bootstrap for local demo only.

CREATE TABLE IF NOT EXISTS bank_user_credentials (
    user_id       UUID PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bank_user_credentials_username
    ON bank_user_credentials(username);

REVOKE ALL ON TABLE public.bank_user_credentials FROM anon, authenticated;
