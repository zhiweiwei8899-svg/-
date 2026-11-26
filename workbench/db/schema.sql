-- 钉钉工作台 · 最小数据模型（v1）
-- 设计原则：不搬原始文件；只存索引与元数据；去重靠 dedup_hash。
-- 中文检索：建 FTS5 external content 表，tokenizer 用 trigram（SQLite >= 3.34）。

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 会话（群 / 单聊）
CREATE TABLE IF NOT EXISTS conversations (
    conv_id       TEXT PRIMARY KEY,
    conv_type     TEXT NOT NULL CHECK (conv_type IN ('group', 'p2p')),
    conv_name     TEXT,
    updated_at    TEXT
);

-- 消息主体。raw_json 保留原始报文，便于字段映射修正后重解析。
CREATE TABLE IF NOT EXISTS messages (
    msg_id        TEXT PRIMARY KEY,
    conv_id       TEXT NOT NULL REFERENCES conversations(conv_id),
    sender_id     TEXT,
    sender_name   TEXT,
    sent_at       TEXT NOT NULL,          -- ISO8601
    msg_type      TEXT NOT NULL,          -- text/image/file/audio/video/card/system
    text          TEXT,
    raw_json      TEXT,
    dedup_hash    TEXT NOT NULL,
    ingested_at   TEXT NOT NULL,
    UNIQUE (dedup_hash)
);

CREATE INDEX IF NOT EXISTS idx_messages_conv_time ON messages(conv_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(sent_at);

-- 文件元数据（原件留在钉钉，按需下载）
CREATE TABLE IF NOT EXISTS attachments (
    att_id        TEXT PRIMARY KEY,
    msg_id        TEXT REFERENCES messages(msg_id),
    file_name     TEXT,
    file_type     TEXT,
    size_bytes    INTEGER,
    download_code TEXT,                   -- 钉钉文件消息里的 downloadCode
    local_path    TEXT,
    parsed_path   TEXT,
    parse_status  TEXT DEFAULT 'pending'  -- pending/done/failed
);

CREATE INDEX IF NOT EXISTS idx_att_msg ON attachments(msg_id);

-- 同步游标：每个数据源一条，记录最后一次成功同步的位置
CREATE TABLE IF NOT EXISTS sync_state (
    source        TEXT PRIMARY KEY,       -- dws:event / dws:wiki / dws:drive
    cursor        TEXT,
    last_run_at   TEXT,
    last_error    TEXT
);

-- 全文检索（trigram：支持中文子串，>=3 字符；<3 字符的查询走 LIKE 兜底）
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text,
    content='messages',
    content_rowid='rowid',
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text) VALUES (new.rowid, COALESCE(new.text, ''));
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text) VALUES ('delete', old.rowid, COALESCE(old.text, ''));
END;
