use serde::{Deserialize, Serialize};
use sqlx::FromRow;

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct ImageRecord {
    pub id: i64,
    pub slug: String,
    pub path: String,
    pub game: String,
    pub characters: Option<String>,
    pub tags: Option<String>,
    pub dominant_color: Option<String>,
    pub hue: Option<i32>,
    pub saturation: Option<i32>,
    pub value: Option<i32>,
    pub orientation: String,
    pub width: i32,
    pub height: i32,
    pub file_size: i32,
    pub blurhash: Option<String>,
    pub phash: Option<String>,
    pub thumbnail_path: Option<String>,
    pub source_type: String,
    pub source_url: Option<String>,
    pub artist: Option<String>,
    pub authorization: String,
    pub is_ai: bool,
    pub weight: i32,
    pub random_key: f64,
    pub status: String,
    pub review_comment: Option<String>,
    pub submitter_contact: Option<String>,
    pub md5_hash: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Deserialize)]
pub struct RandomQuery {
    /// 接受 1/true 或不传 => 302
    pub json: Option<String>,
    pub game: Option<String>,
    pub orientation: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct RandomResponse {
    pub id: String,
    pub url: String,
    pub thumbnail_url: Option<String>,
    pub game: String,
    pub characters: Option<Vec<String>>,
    pub tags: Option<Vec<String>>,
    pub dominant_color: Option<String>,
    pub hue: Option<i32>,
    pub saturation: Option<i32>,
    pub value: Option<i32>,
    pub orientation: String,
    pub width: i32,
    pub height: i32,
    pub file_size: i32,
    pub blurhash: Option<String>,
    pub phash: Option<String>,
    pub source_type: String,
    pub source_url: Option<String>,
    pub artist: Option<String>,
    pub authorization: String,
    pub is_ai: bool,
}

impl From<(ImageRecord, &str)> for RandomResponse {
    fn from((rec, cdn_base): (ImageRecord, &str)) -> Self {
        Self {
            id: rec.slug,
            url: format!("{}/{}", cdn_base, rec.path),
            thumbnail_url: rec
                .thumbnail_path
                .map(|t| format!("{cdn_base}/{t}")),
            game: rec.game,
            characters: rec.characters.and_then(|s| serde_json::from_str(&s).ok()),
            tags: rec.tags.and_then(|s| serde_json::from_str(&s).ok()),
            dominant_color: rec.dominant_color,
            hue: rec.hue,
            saturation: rec.saturation,
            value: rec.value,
            orientation: rec.orientation,
            width: rec.width,
            height: rec.height,
            file_size: rec.file_size,
            blurhash: rec.blurhash,
            phash: rec.phash,
            source_type: rec.source_type,
            source_url: rec.source_url,
            artist: rec.artist,
            authorization: rec.authorization,
            is_ai: rec.is_ai,
        }
    }
}

#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct Category {
    pub game: String,
    pub count: i64,
}

// ---- Admin 模型 ----

#[derive(Debug, Deserialize)]
pub struct ImageQuery {
    pub status: Option<String>,
    pub page: Option<u32>,
    pub per_page: Option<u32>,
}

#[derive(Debug, Serialize)]
pub struct PaginatedImages {
    pub images: Vec<ImageRecord>,
    pub total: i64,
    pub page: u32,
    pub per_page: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageUpdate {
    pub game: Option<String>,
    pub characters: Option<Option<String>>,
    pub tags: Option<Option<String>>,
    pub dominant_color: Option<Option<String>>,
    pub hue: Option<Option<i32>>,
    pub saturation: Option<Option<i32>>,
    pub value: Option<Option<i32>>,
    pub orientation: Option<String>,
    pub source_type: Option<String>,
    pub source_url: Option<Option<String>>,
    pub artist: Option<Option<String>>,
    pub authorization: Option<String>,
    pub is_ai: Option<bool>,
    pub weight: Option<i32>,
    pub status: Option<String>,
    pub review_comment: Option<Option<String>>,
    pub blurhash: Option<Option<String>>,
    pub thumbnail_path: Option<Option<String>>,
}

#[derive(Debug, Serialize)]
pub struct AdminStats {
    pub total: i64,
    pub pending_review: i64,
    pub approved: i64,
    pub rejected: i64,
}
