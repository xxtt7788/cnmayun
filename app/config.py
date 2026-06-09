from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    return int(_env_str(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(_env_str(name, str(default)))


@dataclass(frozen=True)
class Settings:
    app_name: str = "中国上市公司高管与董事变动追踪"
    base_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = base_dir / "data"
    project_memory_path: Path = data_dir / "project_memory.json"
    app_env: str = os.getenv("APP_ENV", "development").lower()
    public_base_url: str = os.getenv("APP_PUBLIC_BASE_URL", "")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/china_succession.db")
    secret_key: str = os.getenv("APP_SECRET_KEY", "change-me-before-production")
    admin_password: str = os.getenv("APP_ADMIN_PASSWORD", "")
    session_cookie_secure_override: str = os.getenv("APP_SESSION_COOKIE_SECURE", "")
    smtp_host: str = os.getenv("ALERT_SMTP_HOST", "")
    smtp_port: int = _env_int("ALERT_SMTP_PORT", 587)
    smtp_username: str = os.getenv("ALERT_SMTP_USERNAME", "")
    smtp_password: str = os.getenv("ALERT_SMTP_PASSWORD", "")
    alert_from_email: str = os.getenv("ALERT_FROM_EMAIL", "")
    webhook_url: str = os.getenv("ALERT_WEBHOOK_URL", "")

    cninfo_stock_list_url: str = "https://www.cninfo.com.cn/new/data/szse_stock.json"
    cninfo_company_intro_url: str = "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction"
    cninfo_company_executives_url: str = "https://www.cninfo.com.cn/data20/companyOverview/getCompanyExecutives"
    cninfo_notice_search_url: str = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    cninfo_notice_detail_base_url: str = "https://static.cninfo.com.cn/"

    cninfo_request_timeout: int = _env_int("CNINFO_REQUEST_TIMEOUT", 30)
    cninfo_request_retries: int = _env_int("CNINFO_REQUEST_RETRIES", 4)
    cninfo_retry_backoff_seconds: float = _env_float("CNINFO_RETRY_BACKOFF_SECONDS", 1.5)

    notice_sync_days_back: int = _env_int("NOTICE_SYNC_DAYS_BACK", 30)
    notice_sync_page_size: int = _env_int("NOTICE_SYNC_PAGE_SIZE", 40)
    notice_sync_page_limit: int = _env_int("NOTICE_SYNC_PAGE_LIMIT", 8)
    notice_pdf_page_limit: int = _env_int("NOTICE_PDF_PAGE_LIMIT", 12)
    notice_text_char_limit: int = _env_int("NOTICE_TEXT_CHAR_LIMIT", 30000)
    low_confidence_threshold: float = _env_float("LOW_CONFIDENCE_THRESHOLD", 0.90)
    ai_extraction_enabled: bool = os.getenv("AI_EXTRACTION_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    ai_api_base_url: str = os.getenv("AI_API_BASE_URL", "")
    ai_api_key: str = os.getenv("AI_API_KEY", "")
    ai_model_name: str = os.getenv("AI_MODEL_NAME", "moonshot-v1-8k")
    ai_request_timeout: int = _env_int("AI_REQUEST_TIMEOUT", 60)
    ai_text_char_limit: int = _env_int("AI_TEXT_CHAR_LIMIT", 12000)

    notice_keywords: tuple[str, ...] = (
        "董事长",
        "总经理",
        "总裁",
        "CEO",
        "财务负责人",
        "财务总监",
        "CFO",
        "副总经理",
        "副总裁",
        "董事会秘书",
        "董秘",
        "独立董事",
        "董事辞职",
        "聘任",
        "辞职",
        "提名",
        "换届",
        "补选",
    )

    @property
    def uses_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def secret_key_is_default(self) -> bool:
        return self.secret_key == "change-me-before-production"

    @property
    def auth_enabled(self) -> bool:
        return bool(self.admin_password)

    @property
    def session_cookie_secure(self) -> bool:
        if self.session_cookie_secure_override:
            return self.session_cookie_secure_override.lower() in {"1", "true", "yes", "on"}
        return self.app_env == "production"

    @property
    def external_alerting_configured(self) -> bool:
        has_email = bool(self.smtp_host and self.smtp_username and self.smtp_password and self.alert_from_email)
        has_webhook = bool(self.webhook_url)
        return has_email or has_webhook


settings = Settings()
