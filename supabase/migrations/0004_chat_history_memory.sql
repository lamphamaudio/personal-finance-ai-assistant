CREATE TABLE IF NOT EXISTS app_chat_sessions (
    id              text PRIMARY KEY,
    user_id         text NOT NULL,
    title           text NOT NULL DEFAULT '',
    status          text NOT NULL DEFAULT 'active',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    last_message_at timestamptz,
    metadata_json   jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (status IN ('active', 'archived', 'deleted'))
);

CREATE TABLE IF NOT EXISTS app_chat_messages (
    id            text PRIMARY KEY,
    session_id    text NOT NULL REFERENCES app_chat_sessions(id),
    user_id       text NOT NULL,
    role          text NOT NULL,
    content       text NOT NULL,
    intent        text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (role IN ('user', 'assistant', 'system', 'tool'))
);

CREATE TABLE IF NOT EXISTS app_chat_tool_calls (
    id                       text PRIMARY KEY,
    session_id               text NOT NULL REFERENCES app_chat_sessions(id),
    message_id               text,
    user_id                  text NOT NULL,
    tool_name                text NOT NULL,
    tool_arguments_json      jsonb NOT NULL DEFAULT '{}'::jsonb,
    tool_result_summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    status                   text NOT NULL,
    latency_ms               integer,
    created_at               timestamptz NOT NULL DEFAULT now(),
    error_message            text
);

CREATE TABLE IF NOT EXISTS app_user_memories (
    id           text PRIMARY KEY,
    user_id      text NOT NULL,
    memory_type  text NOT NULL,
    key          text NOT NULL,
    value_json   jsonb NOT NULL DEFAULT '{}'::jsonb,
    source       text NOT NULL DEFAULT 'chat',
    confidence   numeric(4, 3) NOT NULL DEFAULT 1.0,
    status       text NOT NULL DEFAULT 'active',
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz,
    UNIQUE(user_id, memory_type, key)
);

CREATE INDEX IF NOT EXISTS idx_app_chat_sessions_user_last ON app_chat_sessions (user_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_chat_messages_session_created ON app_chat_messages (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_chat_tool_calls_session_created ON app_chat_tool_calls (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_user_memories_user_type ON app_user_memories (user_id, memory_type, status);
