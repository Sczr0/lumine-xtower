pub struct Config {
    pub database_url: String,
    pub cdn_base_url: String,
    pub static_dir: String,
    pub tagging_dir: String,
    pub host: String,
    pub port: u16,
}

impl Config {
    pub fn from_env() -> Self {
        Self {
            database_url: std::env::var("DATABASE_URL")
                .unwrap_or_else(|_| "sqlite://./data/lumine.db".into()),
            cdn_base_url: std::env::var("CDN_BASE_URL")
                .unwrap_or_else(|_| "https://images.xtower.site".into()),
            static_dir: std::env::var("STATIC_DIR")
                .unwrap_or_else(|_| "../frontend/dist".into()),
            tagging_dir: std::env::var("TAGGING_DIR")
                .unwrap_or_else(|_| "static/tagging".into()),
            host: std::env::var("HOST").unwrap_or_else(|_| "0.0.0.0".into()),
            port: std::env::var("PORT")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(3000),
        }
    }
}
