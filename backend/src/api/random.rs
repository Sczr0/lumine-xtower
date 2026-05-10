use axum::{
    extract::{Query, State},
    http::{HeaderMap, HeaderValue},
    response::{IntoResponse, Redirect, Response},
    Json,
};
use std::sync::Arc;

use crate::db::ImageRepository;
use crate::error::AppError;
use crate::models::{RandomQuery, RandomResponse};

pub struct AppState {
    pub repo: Arc<dyn ImageRepository>,
    pub cdn_base_url: String,
}

pub async fn handler(
    State(state): State<Arc<AppState>>,
    Query(query): Query<RandomQuery>,
) -> Result<Response, AppError> {
    let record = state.repo.random(&query).await?;

    // JSON 模式 (?json=1 / ?json=true)
    let is_json = query.json.as_deref().map_or(false, |v| {
        matches!(v, "1" | "true" | "True" | "TRUE" | "yes" | "Yes")
    });
    if is_json {
        let resp = RandomResponse::from((record, state.cdn_base_url.as_str()));
        return Ok(Json(resp).into_response());
    }

    // 302 重定向模式
    let cdn_url = format!("{}/{}", state.cdn_base_url, record.path);
    let mut headers = HeaderMap::new();
    headers.insert("X-TOS", HeaderValue::from_static("https://lumine.xtower.site/terms"));
    headers.insert("X-Privacy", HeaderValue::from_static("https://lumine.xtower.site/privacy"));
    headers.insert("X-API-Version", HeaderValue::from_static("1.0.0"));

    let redirect = Redirect::temporary(&cdn_url);
    let mut resp = redirect.into_response();
    resp.headers_mut().extend(headers);
    Ok(resp)
}
