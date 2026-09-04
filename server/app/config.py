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

    parse_cache_seconds: int = 60

    jwt_secret: str = "dev-secret-change-me-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 30

    wechat_appid: str = ""
    wechat_secret: str = ""

    enable_watermarked_video: bool = False
    enable_clean_video: bool = False
    enable_audio: bool = False
    enable_comment: bool = True
    enable_danmaku: bool = True
    enable_robot_guide: bool = True
    enable_share: bool = True

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
    robot_poll_interval_seconds: int = 30
    robot_send_interval_seconds: int = 5
    robot_follow_window_seconds: int = 1800

    # 后台管理端（PC Web，独立端口）
    admin_port: int = 8081
    admin_password: str = "admin-dev-password"

    # Cookie 失效告警
    alert_enabled: bool = False
    alert_email: str = ""
    cookie_check_interval_seconds: int = 1800

    # SMTP（告警邮件）
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_pass: str = ""

    # 帮助与反馈页展示的 QQ 群号（默认为空，可后台配置）
    help_qq_group: str = ""


settings = Settings()
