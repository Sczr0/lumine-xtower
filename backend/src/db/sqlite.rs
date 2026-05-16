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

        // WAL 模式 + 性能 pragmas
        let conn_opts = SqliteConnectOptions::from_str(database_url)
            .unwrap_or_else(|_| SqliteConnectOptions::new().filename(db_path))
            .create_if_missing(true)
            .pragma("journal_mode", "WAL")
            .pragma("busy_timeout", "5000")
            .pragma("synchronous", "NORMAL")
            .pragma("cache_size", "-64000")
            .pragma("foreign_keys", "ON");

        let pool = SqlitePoolOptions::new()
            .max_connections(4)
            .min_connections(1)
            .acquire_timeout(std::time::Duration::from_secs(5))
            .idle_timeout(std::time::Duration::from_secs(300))
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
        use sqlx::QueryBuilder;

        let rn: f64 = rand::random();

        // 查询 1: >= 随机 key
        {
            let mut qb = QueryBuilder::<sqlx::Sqlite>::new("SELECT ");
            qb.push(SELECT_FIELDS)
              .push(" FROM images WHERE status = 'approved'");
            if let Some(ref g) = query.game { qb.push(" AND game = ").push_bind(g); }
            if let Some(ref o) = query.orientation { qb.push(" AND orientation = ").push_bind(o); }
            qb.push(" AND random_key >= ").push_bind(rn)
              .push(" ORDER BY random_key ASC LIMIT 1");
            if let Some(row) = qb.build_query_as::<ImageRecord>()
                .fetch_optional(&self.pool).await?
            {
                return Ok(row);
            }
        }

        // 查询 2: 回补（key 最小的那条）
        {
            let mut qb = QueryBuilder::<sqlx::Sqlite>::new("SELECT ");
            qb.push(SELECT_FIELDS)
              .push(" FROM images WHERE status = 'approved'");
            if let Some(ref g) = query.game { qb.push(" AND game = ").push_bind(g); }
            if let Some(ref o) = query.orientation { qb.push(" AND orientation = ").push_bind(o); }
            qb.push(" ORDER BY random_key ASC LIMIT 1");
            qb.build_query_as::<ImageRecord>()
                .fetch_optional(&self.pool)
                .await?
                .ok_or_else(|| AppError::NotFound("no images match the criteria".into()))
        }
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
        use sqlx::QueryBuilder;

        let page = query.page.unwrap_or(1).max(1);
        let per_page = query.per_page.unwrap_or(50).min(200);
        let offset = (page - 1) * per_page;

        let total: i64 = if let Some(ref status) = query.status {
            sqlx::query_scalar("SELECT COUNT(*) FROM images WHERE status = ?")
                .bind(status)
                .fetch_one(&self.pool).await?
        } else {
            sqlx::query_scalar("SELECT COUNT(*) FROM images")
                .fetch_one(&self.pool).await?
        };

        let images = if let Some(ref status) = query.status {
            let mut qb = QueryBuilder::new("SELECT ");
            qb.push(SELECT_FIELDS)
              .push(" FROM images WHERE status = ")
              .push_bind(status)
              .push(" ORDER BY created_at DESC LIMIT ")
              .push_bind(per_page as i64)
              .push(" OFFSET ")
              .push_bind(offset as i64);
            qb.build_query_as::<ImageRecord>().fetch_all(&self.pool).await?
        } else {
            let mut qb = QueryBuilder::new("SELECT ");
            qb.push(SELECT_FIELDS)
              .push(" FROM images ORDER BY created_at DESC LIMIT ")
              .push_bind(per_page as i64)
              .push(" OFFSET ")
              .push_bind(offset as i64);
            qb.build_query_as::<ImageRecord>().fetch_all(&self.pool).await?
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
        use sqlx::QueryBuilder;

        let mut qb: QueryBuilder<'_, sqlx::Sqlite> = QueryBuilder::new("UPDATE images SET ");
        let mut separated = qb.separated(", ");

        let mut field_count = 0;
        if let Some(ref v) = update.characters { separated.push("characters = ").push_bind(v.as_deref()); field_count += 1; }
        if let Some(ref v) = update.tags { separated.push("tags = ").push_bind(v.as_deref()); field_count += 1; }
        if let Some(ref v) = update.dominant_color { separated.push("dominant_color = ").push_bind(v.as_deref()); field_count += 1; }
        if let Some(ref v) = update.source_url { separated.push("source_url = ").push_bind(v.as_deref()); field_count += 1; }
        if let Some(ref v) = update.artist { separated.push("artist = ").push_bind(v.as_deref()); field_count += 1; }
        if let Some(ref v) = update.review_comment { separated.push("review_comment = ").push_bind(v.as_deref()); field_count += 1; }
        if let Some(ref v) = update.blurhash { separated.push("blurhash = ").push_bind(v.as_deref()); field_count += 1; }
        if let Some(ref v) = update.thumbnail_path { separated.push("thumbnail_path = ").push_bind(v.as_deref()); field_count += 1; }
        if let Some(v) = update.hue { separated.push("hue = ").push_bind(v); field_count += 1; }
        if let Some(v) = update.saturation { separated.push("saturation = ").push_bind(v); field_count += 1; }
        if let Some(v) = update.value { separated.push("value = ").push_bind(v); field_count += 1; }
        if let Some(ref v) = update.game { separated.push("game = ").push_bind(v); field_count += 1; }
        if let Some(ref v) = update.orientation { separated.push("orientation = ").push_bind(v); field_count += 1; }
        if let Some(ref v) = update.source_type { separated.push("source_type = ").push_bind(v); field_count += 1; }
        if let Some(ref v) = update.authorization { separated.push("authorization = ").push_bind(v); field_count += 1; }
        if let Some(ref v) = update.status { separated.push("status = ").push_bind(v); field_count += 1; }
        if let Some(v) = update.weight { separated.push("weight = ").push_bind(v); field_count += 1; }
        if let Some(v) = update.is_ai { separated.push("is_ai = ").push_bind(v); field_count += 1; }

        if field_count == 0 {
            return Err(AppError::BadRequest("no fields to update".into()));
        }

        qb.push(" WHERE slug = ").push_bind(slug);
        let result = qb.build().execute(&self.pool).await?;
        if result.rows_affected() == 0 {
            return Err(AppError::NotFound(format!("image `{slug}` not found")));
        }
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
