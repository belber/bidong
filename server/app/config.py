from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "bili-collector"
    dev_mode: bool = True

    database_url: str = "sqlite:///./var/bili.db"

    jwt_secret: str = "dev-secret-change-me-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 30

    wechat_appid: str = ""
    wechat_secret: str = ""

    enable_watermarked_video: bool = False
    enable_clean_video: bool = False
    enable_audio: bool = False

    storage_backend: str = "local"
    local_storage_dir: str = "./var/covers"
    public_base_url: str = "http://127.0.0.1:8000"

    cos_secret_id: str = ""
    cos_secret_key: str = ""
    cos_bucket: str = ""
    cos_region: str = ""

    robot_enabled: bool = False
    robot_uid: str = ""
    robot_sessdata: str = ""
    robot_bili_jct: str = ""
    robot_dedeuserid: str = ""
    robot_buvid3: str = ""
    robot_buvid4: str = ""
    robot_poll_interval_seconds: int = 45
    robot_send_interval_seconds: int = 5


settings = Settings()
