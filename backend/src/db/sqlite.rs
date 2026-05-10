use async_trait::async_trait;
use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
use sqlx::SqlitePool;
use tracing::info;
use std::str::FromStr;

use crate::error::AppError;
use crate::models::{
    AdminStats, Category, ImageQuery, ImageRecord, ImageUpdate, PaginatedImages, RandomQuery,
};

use super::ImageRepository;

/// 公共 SELECT 字段列表
const SELECT_FIELDS: &str = r#"id, slug, path, game, characters, tags,
    dominant_color, hue, saturation, value, orientation,
    width, height, file_size, blurhash, phash, thumbnail_path,
    source_type, source_url, artist, authorization,
    is_ai, weight, random_key, status,
    review_comment, submitter_contact, md5_hash, created_at"#;

pub struct SqliteRepo {
    pub pool: SqlitePool,
}

impl SqliteRepo {
    pub async fn new(database_url: &str) -> Result<Self, sqlx::Error> {
        // 从 URL 中提取真实文件路径
        let db_path = database_url
            .strip_prefix("sqlite:///")
            .or_else(|| {
                database_url
                    .strip_prefix("sqlite://")
                    .and_then(|s| s.strip_prefix('.'))
            })
            .or_else(|| database_url.strip_prefix("sqlite:"))
            .unwrap_or(database_url);

        // 确保目录存在
        if let Some(parent) = std::path::Path::new(db_path).parent() {
            if !parent.as_os_str().is_empty() {
                std::fs::create_dir_all(parent).map_err(|e| {
                    tracing::warn!("failed to create db directory {parent:?}: {e}");
                    e
                }).ok();
            }
        }

        // 使用 SqliteConnectOptions 精确控制，避免 URL 解析差异
        let conn_opts = SqliteConnectOptions::from_str(database_url)
            .unwrap_or_else(|_| SqliteConnectOptions::new().filename(db_path))
            .create_if_missing(true);

        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect_with(conn_opts)
            .await?;

        info!("SQLite pool created: {database_url}");
        Ok(Self { pool })
    }

    pub async fn run_migrations(&self) -> Result<(), sqlx::Error> {
        let sql = include_str!("../../migrations/001_initial.sql");
        sqlx::raw_sql(sql).execute(&self.pool).await?;
        info!("Database migrations applied");
        Ok(())
    }

    #[allow(dead_code)]
    pub async fn insert(&self, record: &ImageRecord) -> Result<(), sqlx::Error> {
        sqlx::query(
            r#"INSERT OR IGNORE INTO images
               (slug, path, game, characters, tags,
                dominant_color, hue, saturation, value, orientation,
                width, height, file_size, blurhash, phash, thumbnail_path,
                source_type, source_url, artist, authorization,
                is_ai, weight, random_key, status,
                review_comment, submitter_contact, md5_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?, ?)"#,
        )
        .bind(&record.slug)
        .bind(&record.path)
        .bind(&record.game)
        .bind(&record.characters)
        .bind(&record.tags)
        .bind(&record.dominant_color)
        .bind(record.hue)
        .bind(record.saturation)
        .bind(record.value)
        .bind(&record.orientation)
        .bind(record.width)
        .bind(record.height)
        .bind(record.file_size)
        .bind(&record.blurhash)
        .bind(&record.phash)
        .bind(&record.thumbnail_path)
        .bind(&record.source_type)
        .bind(&record.source_url)
        .bind(&record.artist)
        .bind(&record.authorization)
        .bind(record.is_ai)
        .bind(record.weight)
        .bind(record.random_key)
        .bind(&record.status)
        .bind(&record.review_comment)
        .bind(&record.submitter_contact)
        .bind(&record.md5_hash)
        .bind(&record.created_at)
        .execute(&self.pool)
        .await?;
        Ok(())
    }
}

#[async_trait]
impl ImageRepository for SqliteRepo {
    // ========== 公开 API ==========

    async fn random(&self, query: &RandomQuery) -> Result<ImageRecord, AppError> {
        let rn: f64 = rand::random();

        let mut where_clause = String::from("status = 'approved'");
        if query.game.is_some() {
            where_clause.push_str(" AND game = ?");
        }
        if query.orientation.is_some() {
            where_clause.push_str(" AND orientation = ?");
        }

        // 查询 1: >= 随机 key
        let sql1 = format!(
            "SELECT {SELECT_FIELDS} FROM images WHERE {where_clause} AND random_key >= ? \
             ORDER BY random_key ASC LIMIT 1"
        );
        let mut q1 = sqlx::query_as::<_, ImageRecord>(&sql1);
        if let Some(ref g) = query.game { q1 = q1.bind(g); }
        if let Some(ref o) = query.orientation { q1 = q1.bind(o); }
        q1 = q1.bind(rn);

        if let Some(row) = q1.fetch_optional(&self.pool).await? {
            return Ok(row);
        }

        // 查询 2: 回补
        let sql2 = format!(
            "SELECT {SELECT_FIELDS} FROM images WHERE {where_clause} \
             ORDER BY random_key ASC LIMIT 1"
        );
        let mut q2 = sqlx::query_as::<_, ImageRecord>(&sql2);
        if let Some(ref g) = query.game { q2 = q2.bind(g); }
        if let Some(ref o) = query.orientation { q2 = q2.bind(o); }

        q2.fetch_optional(&self.pool)
            .await?
            .ok_or_else(|| AppError::NotFound("no images match the criteria".into()))
    }

    async fn categories(&self) -> Result<Vec<Category>, AppError> {
        let rows = sqlx::query_as::<_, Category>(
            "SELECT game, COUNT(*) as \"count\" FROM images WHERE status = 'approved' \
             GROUP BY game ORDER BY count DESC",
        )
        .fetch_all(&self.pool)
        .await?;
        Ok(rows)
    }

    // ========== Admin API ==========

    async fn list_images(&self, query: &ImageQuery) -> Result<PaginatedImages, AppError> {
        let page = query.page.unwrap_or(1).max(1);
        let per_page = query.per_page.unwrap_or(50).min(200);
        let offset = (page - 1) * per_page;
        let has = query.status.is_some();

        let total: i64 = if has {
            sqlx::query_scalar("SELECT COUNT(*) FROM images WHERE status = ?")
                .bind(query.status.as_ref().unwrap())
                .fetch_one(&self.pool).await?
        } else {
            sqlx::query_scalar("SELECT COUNT(*) FROM images")
                .fetch_one(&self.pool).await?
        };

        let images = if has {
            sqlx::query_as::<_, ImageRecord>(&format!(
                "SELECT {SELECT_FIELDS} FROM images WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?"
            ))
            .bind(query.status.as_ref().unwrap())
            .bind(per_page as i64).bind(offset as i64)
            .fetch_all(&self.pool).await?
        } else {
            sqlx::query_as::<_, ImageRecord>(&format!(
                "SELECT {SELECT_FIELDS} FROM images ORDER BY created_at DESC LIMIT ? OFFSET ?"
            ))
            .bind(per_page as i64).bind(offset as i64)
            .fetch_all(&self.pool).await?
        };

        Ok(PaginatedImages { images, total, page, per_page })
    }

    async fn get_image(&self, slug: &str) -> Result<ImageRecord, AppError> {
        sqlx::query_as::<_, ImageRecord>(&format!(
            "SELECT {SELECT_FIELDS} FROM images WHERE slug = ?"
        ))
        .bind(slug)
        .fetch_optional(&self.pool)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("image `{slug}` not found")))
    }

    async fn update_image(&self, slug: &str, update: &ImageUpdate) -> Result<(), AppError> {
        self.get_image(slug).await?;

        let mut set_clauses: Vec<&str> = Vec::new();
        let mut b_null_s: Vec<Option<String>> = Vec::new();
        let mut b_null_i: Vec<Option<i32>> = Vec::new();
        let mut b_req_s: Vec<String> = Vec::new();
        let mut b_req_i: Vec<i32> = Vec::new();
        let mut b_req_b: Vec<bool> = Vec::new();

        for (cl, v) in &[
            ("characters = ?", &update.characters),
            ("tags = ?", &update.tags),
            ("dominant_color = ?", &update.dominant_color),
            ("source_url = ?", &update.source_url),
            ("artist = ?", &update.artist),
            ("review_comment = ?", &update.review_comment),
            ("blurhash = ?", &update.blurhash),
            ("thumbnail_path = ?", &update.thumbnail_path),
        ] {
            if let Some(ref vv) = v {
                set_clauses.push(cl);
                b_null_s.push(vv.clone());
            }
        }

        for (cl, v) in &[
            ("hue = ?", &update.hue),
            ("saturation = ?", &update.saturation),
            ("value = ?", &update.value),
        ] {
            if let Some(ref vv) = v {
                set_clauses.push(cl);
                b_null_i.push(*vv);
            }
        }

        for (cl, v) in &[
            ("game = ?", &update.game),
            ("orientation = ?", &update.orientation),
            ("source_type = ?", &update.source_type),
            ("authorization = ?", &update.authorization),
            ("status = ?", &update.status),
        ] {
            if let Some(ref vv) = v {
                set_clauses.push(cl);
                b_req_s.push(vv.clone());
            }
        }

        if let Some(ref v) = update.weight {
            set_clauses.push("weight = ?");
            b_req_i.push(*v);
        }
        if let Some(ref v) = update.is_ai {
            set_clauses.push("is_ai = ?");
            b_req_b.push(*v);
        }

        if set_clauses.is_empty() {
            return Err(AppError::BadRequest("no fields to update".into()));
        }

        let sql = format!("UPDATE images SET {} WHERE slug = ?", set_clauses.join(", "));
        let mut q = sqlx::query(&sql);
        for v in &b_null_s { q = q.bind(v.as_deref()); }
        for v in &b_null_i { q = q.bind(*v); }
        for v in &b_req_s { q = q.bind(v); }
        for v in &b_req_i { q = q.bind(v); }
        for v in &b_req_b { q = q.bind(v); }
        q = q.bind(slug);
        q.execute(&self.pool).await?;
        Ok(())
    }

    async fn stats(&self) -> Result<AdminStats, AppError> {
        let row = sqlx::query_as::<_, (i64, i64, i64, i64)>(
            "SELECT COUNT(*), \
             COALESCE(SUM(CASE WHEN status = 'pending_review' THEN 1 ELSE 0 END), 0), \
             COALESCE(SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END), 0), \
             COALESCE(SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END), 0) \
             FROM images",
        )
        .fetch_one(&self.pool)
        .await?;
        Ok(AdminStats { total: row.0, pending_review: row.1, approved: row.2, rejected: row.3 })
    }
}
