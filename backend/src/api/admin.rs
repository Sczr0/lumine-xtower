use axum::{
    extract::{Path, Query, State},
    http::{HeaderMap, StatusCode},
    middleware,
    response::IntoResponse,
    Json, Router,
};
use std::sync::Arc;

use crate::error::AppError;
use crate::models::{ImageQuery, ImageUpdate, PaginatedImages};
use super::random::AppState;

/// 鉴权中间件
async fn auth_middleware(
    headers: HeaderMap,
    req: axum::extract::Request,
    next: middleware::Next,
) -> Result<impl IntoResponse, StatusCode> {
    if let Some(email) = headers.get("Cf-Access-Authenticated-User-Email") {
        if !email.to_str().unwrap_or("").is_empty() {
            return Ok(next.run(req).await);
        }
    }
    let admin_token = std::env::var("ADMIN_TOKEN").ok();
    if let Some(expected) = admin_token {
        if let Some(auth) = headers.get("Authorization") {
            if let Ok(val) = auth.to_str() {
                if val == format!("Bearer {expected}") {
                    return Ok(next.run(req).await);
                }
            }
        }
        return Err(StatusCode::UNAUTHORIZED);
    }
    Ok(next.run(req).await)
}

pub fn routes(state: Arc<AppState>) -> Router<Arc<AppState>> {
    Router::new()
        .route("/admin/images", axum::routing::get(list_images))
        .route("/admin/images/:slug", axum::routing::get(get_image))
        .route("/admin/images/:slug", axum::routing::patch(update_image))
        .route("/admin/stats", axum::routing::get(stats))
        .route_layer(middleware::from_fn(auth_middleware))
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
