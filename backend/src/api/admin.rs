use axum::{
    extract::{Path, Query, State},
    http::{HeaderMap, StatusCode},
    middleware,
    response::IntoResponse,
    Json, Router,
};
use std::sync::Arc;
use tower_http::limit::RequestBodyLimitLayer;

use crate::error::AppError;
use crate::models::{ImageQuery, ImageUpdate, PaginatedImages};
use super::random::AppState;

/// 鉴权中间件
async fn auth_middleware(
    headers: HeaderMap,
    req: axum::extract::Request,
    next: middleware::Next,
) -> Result<impl IntoResponse, StatusCode> {
    // 方式 1: Cloudflare Zero Trust 鉴权
    if let Some(email) = headers.get("Cf-Access-Authenticated-User-Email") {
        if !email.to_str().unwrap_or_default().is_empty() {
            return Ok(next.run(req).await);
        }
    }
    // 方式 2: Bearer token 鉴权（必须配置 ADMIN_TOKEN 才会生效）
    match std::env::var("ADMIN_TOKEN") {
        Ok(expected) if !expected.is_empty() => {
            let auth_val = headers
                .get("Authorization")
                .and_then(|v| v.to_str().ok())
                .unwrap_or("");
            if auth_val == format!("Bearer {expected}") {
                return Ok(next.run(req).await);
            }
            Err(StatusCode::UNAUTHORIZED)
        }
        _ => Err(StatusCode::UNAUTHORIZED),
    }
}

pub fn routes(state: Arc<AppState>) -> Router<Arc<AppState>> {
    Router::new()
        .route("/admin/images", axum::routing::get(list_images))
        .route("/admin/images/:slug", axum::routing::get(get_image))
        .route("/admin/images/:slug", axum::routing::patch(update_image))
        .route("/admin/stats", axum::routing::get(stats))
        .route_layer(middleware::from_fn(auth_middleware))
        .layer(RequestBodyLimitLayer::new(1024 * 1024)) // 1MB 限制
        .with_state(state)
}

async fn list_images(
    State(state): State<Arc<AppState>>,
    Query(query): Query<ImageQuery>,
) -> Result<Json<PaginatedImages>, AppError> {
    let result = state.repo.list_images(&query).await?;
    Ok(Json(result))
}

async fn get_image(
    State(state): State<Arc<AppState>>,
    Path(slug): Path<String>,
) -> Result<Json<crate::models::ImageRecord>, AppError> {
    let record = state.repo.get_image(&slug).await?;
    Ok(Json(record))
}

async fn update_image(
    State(state): State<Arc<AppState>>,
    Path(slug): Path<String>,
    Json(update): Json<ImageUpdate>,
) -> Result<impl IntoResponse, AppError> {
    state.repo.update_image(&slug, &update).await?;
    Ok(StatusCode::NO_CONTENT)
}

async fn stats(
    State(state): State<Arc<AppState>>,
) -> Result<Json<crate::models::AdminStats>, AppError> {
    let s = state.repo.stats().await?;
    Ok(Json(s))
}
