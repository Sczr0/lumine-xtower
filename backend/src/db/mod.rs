pub mod sqlite;

use async_trait::async_trait;
use crate::error::AppError;
use crate::models::{
    AdminStats, Category, ImageQuery, ImageRecord, ImageUpdate, PaginatedImages, RandomQuery,
};

#[async_trait]
pub trait ImageRepository: Send + Sync {
    // 公开 API
    async fn random(&self, query: &RandomQuery) -> Result<ImageRecord, AppError>;
    async fn categories(&self) -> Result<Vec<Category>, AppError>;

    // Admin API
    async fn list_images(&self, query: &ImageQuery) -> Result<PaginatedImages, AppError>;
    async fn get_image(&self, id: &str) -> Result<ImageRecord, AppError>;
    async fn update_image(&self, id: &str, update: &ImageUpdate) -> Result<(), AppError>;
    async fn stats(&self) -> Result<AdminStats, AppError>;
}
