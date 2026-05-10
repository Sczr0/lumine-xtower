mod api;
mod config;
mod db;
mod error;
mod models;

use std::sync::Arc;

use axum::{routing::get, Router};
use tower_http::services::ServeDir;
use tracing_subscriber::EnvFilter;

use crate::api::random::AppState;
use crate::config::Config;
use crate::db::sqlite::SqliteRepo;
use crate::db::ImageRepository;

#[tokio::main]
async fn main() {
    dotenvy::dotenv().ok();

    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    let config = Config::from_env();

    tracing::info!("CDN_BASE_URL = {}", config.cdn_base_url);

    // 初始化数据库
    let repo = SqliteRepo::new(&config.database_url)
        .await
        .expect("failed to connect to database");
    repo.run_migrations()
        .await
        .expect("failed to run migrations");

    let state = Arc::new(AppState {
        repo: Arc::new(repo) as Arc<dyn ImageRepository>,
        cdn_base_url: config.cdn_base_url.clone(),
    });

    // 路由（具体路径优先于泛路径）
    let app = Router::new()
        // 公开 API
        .route("/v1/random", get(api::random::handler))
        .route("/v1/categories", get(api::categories::handler))
        // Admin API（鉴权在此路由层内部）
        .merge(api::admin::routes(state.clone()))
        // 打标 SPA（构建产物在 backend/static/tagging/）
        .nest_service("/tagging", ServeDir::new(&config.tagging_dir))
        // 前端 Astro 构建产物（catch-all）
        .nest_service("/", ServeDir::new(&config.static_dir))
        .with_state(state);

    let addr = format!("{}:{}", config.host, config.port);
    tracing::info!("Server starting on {addr}");

    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .expect("failed to bind address");
    axum::serve(listener, app)
        .await
        .expect("server error");
}
