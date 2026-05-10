use axum::{extract::State, Json};
use std::sync::Arc;

use crate::error::AppError;

use super::random::AppState;

pub async fn handler(
    State(state): State<Arc<AppState>>,
) -> Result<impl axum::response::IntoResponse, AppError> {
    let categories = state.repo.categories().await?;
    Ok(([("X-API-Version", "1.0.0")], Json(categories)))
}
