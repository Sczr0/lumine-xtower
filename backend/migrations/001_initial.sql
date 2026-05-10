CREATE TABLE IF NOT EXISTS images (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    slug              TEXT UNIQUE NOT NULL,
    path              TEXT NOT NULL,
    game              TEXT NOT NULL,
    characters        TEXT,
    tags              TEXT,
    dominant_color    TEXT,
    hue               INTEGER,
    saturation        INTEGER,
    value             INTEGER,
    orientation       TEXT NOT NULL,
    width             INTEGER NOT NULL,
    height            INTEGER NOT NULL,
    file_size         INTEGER NOT NULL,
    blurhash          TEXT,
    phash             TEXT,
    thumbnail_path    TEXT,
    source_type       TEXT NOT NULL DEFAULT 'manual',
    source_url        TEXT,
    artist            TEXT,
    authorization     TEXT NOT NULL DEFAULT 'unknown',
    is_ai             INTEGER NOT NULL DEFAULT 0,
    weight            INTEGER NOT NULL DEFAULT 100,
    random_key        REAL NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending_review',
    review_comment    TEXT,
    submitter_contact TEXT,
    md5_hash          TEXT UNIQUE,
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_images_status_random ON images(status, random_key);
CREATE INDEX IF NOT EXISTS idx_images_game ON images(game);
CREATE INDEX IF NOT EXISTS idx_images_md5 ON images(md5_hash);
