"""Configuration for the AR-interior redesign service."""
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings."""

    # API keys
    OPENAI_API_KEY: str | None = None
    OPENAI_ORGANIZATION: str | None = None
    OPENAI_PROJECT: str | None = None
    OPENAI_TEXT_MODEL: str = "gpt-5.2"
    OPENAI_TEXT_TIMEOUT: int = 120
    OPENAI_PLANNER_MAX_OUTPUT_TOKENS: int = 5000
    OPENAI_PLANNER_TEMPERATURE: float = 0.2
    OPENAI_PLANNER_REASONING_EFFORT: str = "high"
    OPENAI_RANKER_MAX_OUTPUT_TOKENS: int = 5000
    OPENAI_RANKER_TEMPERATURE: float = 0.0
    OPENAI_RANKER_REASONING_EFFORT: str = "high"
    OPENAI_TEXT_VERBOSITY: str = "low"
    OPENAI_TEXT_STORE: bool = False
    OPENAI_TEXT_SEND_TEMPERATURE: bool = False
    OPENAI_IMAGE_MODEL: str = "gpt-image-1.5"
    OPENAI_IMAGE_SIZE: str = "1024x1024"
    OPENAI_IMAGE_TIMEOUT: int = 180
    OPENAI_IMAGE_TIMEOUT_CONNECT_SECONDS: int = 20
    OPENAI_IMAGE_TIMEOUT_READ_SECONDS: int = 160
    OPENAI_IMAGE_QUALITY: str = "high"
    OPENAI_IMAGE_OUTPUT_FORMAT: str = "png"
    OPENAI_IMAGE_INPUT_FORMAT: str = "jpeg"
    OPENAI_IMAGE_INPUT_FIDELITY: str = "high"
    OPENAI_IMAGE_INPUT_JPEG_QUALITY: int = 95
    OPENAI_IMAGE_INPUT_MAX_LONG_EDGE: int = 1536
    OPENAI_IMAGE_AUX_MAX_LONG_EDGE: int = 1024
    OPENAI_IMAGE_BACKGROUND: str = "auto"
    OPENAI_IMAGE_MODERATION: str = "auto"
    OPENAI_IMAGE_PARTIAL_IMAGES: int = 0
    OPENAI_IMAGE_INPUT_PRICE_PER_MILLION: float | None = None
    OPENAI_IMAGE_OUTPUT_PRICE_PER_MILLION: float | None = None
    OPENAI_IMAGE_PRICE_TABLE_JSON: str | None = None
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-pro"
    GEMINI_TIMEOUT_SECONDS: int = 60
    GEMINI_MAX_OUTPUT_TOKENS: int = 4096
    VERTEX_PROJECT_ID: str | None = None
    VERTEX_LOCATION: str = "us-central1"
    GOOGLE_CLOUD_CREDENTIALS_PATH: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_CLOUD_CREDENTIALS_PATH", "GOOGLE_APPLICATION_CREDENTIALS"
        ),
    )
    DECOR8_API_KEY: str | None = None
    DECOR8_API_BASE: str = "https://api.decor8.ai"
    DECOR8_TIMEOUT_SECONDS: int = 120
    DECOR8_TIMEOUT_CONNECT_SECONDS: int = 15
    DECOR8_TIMEOUT_READ_SECONDS: int = 110
    GOOGLE_VISION_CREDENTIALS_PATH: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_VISION_CREDENTIALS_PATH"),
    )
    SEARCHAPI_KEY: str | None = None
    TELEGRAM_TOKEN: str | None = None
    APP_MODE: str = "polling"
    WEB_APP_URL: str = "https://app.vizuai.example"
    WEB_PUBLIC_URL: str = "https://vizuai.example"
    WEB_API_URL: str = "https://api.vizuai.example"
    WEB_ALLOWED_ORIGINS: str = "https://app.vizuai.example,http://localhost:3000"
    RESEND_API_KEY: str | None = None
    RESEND_FROM_EMAIL: str | None = None
    POSTMARK_SERVER_TOKEN: str | None = None
    POSTMARK_FROM_EMAIL: str | None = None
    POSTMARK_MESSAGE_STREAM: str | None = None
    AUTH_MAGIC_LINK_TTL_MINUTES: int = 20
    AUTH_SESSION_TTL_DAYS: int = 30
    AUTH_SESSION_TOUCH_INTERVAL_SECONDS: int = 300
    AUTH_SESSION_COOKIE_NAME: str = "vizuai_session"
    WEB_UPLOAD_INTENT_TTL_MINUTES: int = 20
    WEB_MAX_UPLOAD_SIZE_BYTES: int = 15 * 1024 * 1024
    WEB_JOB_QUEUE_STALE_SECONDS: int = 900
    WEB_JOB_PROCESSING_STALE_SECONDS: int = 3600
    WEB_RATE_LIMIT_ENABLED: bool = True
    WEB_RATE_LIMIT_PUBLIC_LIMIT: int = 120
    WEB_RATE_LIMIT_PUBLIC_WINDOW_SECONDS: int = 60
    WEB_RATE_LIMIT_PUBLIC_ANALYTICS_LIMIT: int = 300
    WEB_RATE_LIMIT_PUBLIC_ANALYTICS_WINDOW_SECONDS: int = 60
    WEB_RATE_LIMIT_AUTH_START_LIMIT: int = 6
    WEB_RATE_LIMIT_AUTH_START_WINDOW_SECONDS: int = 900
    WEB_RATE_LIMIT_AUTH_VERIFY_LIMIT: int = 20
    WEB_RATE_LIMIT_AUTH_VERIFY_WINDOW_SECONDS: int = 900
    WEB_RATE_LIMIT_UPLOAD_LIMIT: int = 60
    WEB_RATE_LIMIT_UPLOAD_WINDOW_SECONDS: int = 300
    WEB_RATE_LIMIT_JOB_CREATE_LIMIT: int = 20
    WEB_RATE_LIMIT_JOB_CREATE_WINDOW_SECONDS: int = 900
    WEB_RATE_LIMIT_BILLING_CHECKOUT_LIMIT: int = 10
    WEB_RATE_LIMIT_BILLING_CHECKOUT_WINDOW_SECONDS: int = 900
    WEB_RATE_LIMIT_APP_LIMIT: int = 240
    WEB_RATE_LIMIT_APP_WINDOW_SECONDS: int = 60
    TELEGRAM_WEBHOOK_PATH: str = "/telegram"
    TELEGRAM_WEBHOOK_SECRET: str = ""
    WORKER_PUBLIC_BASE_URL: str | None = None
    CLOUD_TASKS_PROJECT_ID: str | None = None
    CLOUD_TASKS_LOCATION: str = "europe-west1"
    CLOUD_TASKS_QUEUE: str = "telegram-updates"
    CLOUD_TASKS_WORKER_URL: str | None = None
    CLOUD_TASKS_SERVICE_ACCOUNT: str | None = None
    CLOUD_TASKS_REQUEST_SECRET: str = ""
    DATABASE_URL: str | None = None
    TBANK_TERMINAL_KEY: str | None = None
    TBANK_PASSWORD: str | None = None
    TBANK_API_BASE: str = "https://securepay.tinkoff.ru/v2"
    TBANK_NOTIFICATION_PATH: str = "/payments/tbank/notify"
    TBANK_SUCCESS_URL: str | None = None
    TBANK_FAIL_URL: str | None = None
    TBANK_ACCEPT_STATUSES: str = "CONFIRMED,AUTHORIZED"
    TBANK_TIMEOUT_SECONDS: int = 30
    TBANK_PACKAGE_CATALOG_RUB_JSON: str | None = None
    WEB_TBANK_PACKAGE_CATALOG_RUB_JSON: str | None = None
    BILLING_WEBHOOK_MAX_ATTEMPTS: int = 3
    BILLING_WEBHOOK_DEADLETTER_LIMIT: int = 20
    TBANK_RECEIPT_ENABLED: bool = False
    TBANK_RECEIPT_FFD_VERSION: str | None = None
    TBANK_RECEIPT_TAXATION: str = "usn_income"
    TBANK_RECEIPT_EMAIL: str | None = None
    TBANK_RECEIPT_PHONE: str | None = None
    TBANK_RECEIPT_ITEM_NAME: str = "Пакет запросов VizuAI"
    TBANK_RECEIPT_ITEM_TAX: str = "none"
    TBANK_RECEIPT_ITEM_PAYMENT_METHOD: str | None = None
    TBANK_RECEIPT_ITEM_PAYMENT_OBJECT: str | None = None
    # URLs
    SEARCHAPI_BASE_URL: str = "https://www.searchapi.io/api/v1/search"
    SEARCHAPI_ENGINE: str = "google_lens"
    SEARCHAPI_SEARCH_TYPE: str = "products"
    SEARCHAPI_HL: str = "ru"
    SEARCHAPI_COUNTRY: str = "RU"
    SEARCHAPI_DEVICE: str = "desktop"
    SEARCHAPI_TIMEOUT_SECONDS: int = 30
    SEARCHAPI_TIMEOUT_CONNECT_SECONDS: int = 8
    SEARCHAPI_TIMEOUT_READ_SECONDS: int = 25
    SEARCHAPI_RETRY_ATTEMPTS: int = 3
    SEARCHAPI_RETRY_BASE_DELAY: float = 1.0
    SEARCHAPI_RETRY_MAX_DELAY: float = 5.0
    SEARCHAPI_CIRCUIT_BREAKER_ENABLED: bool = True
    SEARCHAPI_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    SEARCHAPI_CIRCUIT_BREAKER_OPEN_SECONDS: int = 45
    SIMPLE_PLANNER_PROMPT_PATH: str = "prompts/gpt_methods_planner_instruction_simple_pipeline_v1.md"
    SIMPLE_PLANNER_STYLE_REF_PROMPT_PATH: str = "prompts/gpt_methods_planner_instruction_simple_pipeline_v1_style_ref.md"
    SIMPLE_RENDER_PROMPT_PATH: str = "prompts/gpt_image15_hardlock_and_role_v1.md"
    SIMPLE_RENDER_STYLE_REF_PROMPT_PATH: str = "prompts/gpt_image15_hardlock_and_role_v1_style_ref.md"
    SIMPLE_RANKER_PROMPT_PATH: str = "prompts/gpt_ranker_ab_prompt_v2.md"
    SIMPLE_RANKER_STYLE_REF_PROMPT_PATH: str = "prompts/gpt_ranker_ab_prompt_v2_style_ref.md"
    PIPELINE_VERSION: str = "simple_v1"
    GCS_BUCKET: str | None = None
    GCS_CREDENTIALS_PATH: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GCS_CREDENTIALS_PATH", "GOOGLE_APPLICATION_CREDENTIALS"),
    )
    S3_PRESIGN_INPUTS: bool = True
    S3_PRESIGN_EXPIRES: int = 3600
    REDIS_URL: str | None = None
    WORKER_GLOBAL_ACTIVE_JOBS_LIMIT: int = 2
    WORKER_GLOBAL_ACTIVE_JOBS_WAIT_SECONDS: float = 1.0
    WORKER_GLOBAL_ACTIVE_JOBS_LEASE_SECONDS: int = 7200
    ADMIN_CHAT_IDS: str = ""

    # Constants
    MAX_OBJECTS: int = 10
    CDN_URL_TEMPLATE: str | None = None
    TIMEOUT: int = 30
    RETRY_ATTEMPTS: int = 3
    RETRY_BASE_DELAY: float = 1.0
    RETRY_MAX_DELAY: float = 8.0
    VISION_MAX_RESULTS: int = 30
    VISION_MIN_SCORE: float = 0.5
    VISION_MIN_AREA: float = 0.01
    VISION_PREFETCH_N: int = 30
    VISION_IOU_THRESHOLD: float = 0.85
    VISION_CONTAINMENT_THRESHOLD: float = 0.90
    VISION_MAX_PER_LABEL: int = 2
    VISION_GENERIC_LABELS: str = "interior,room,indoor,home,house,apartment,building,property"
    VISION_GENERIC_IOU_THRESHOLD: float = 0.85
    VISION_GENERIC_CONTAINMENT_THRESHOLD: float = 0.90
    VISION_DUPLICATE_IOU_THRESHOLD: float = 0.90
    VISION_DUPLICATE_CONTAINMENT_THRESHOLD: float = 0.95
    EXCLUDE_LABELS_PATH: str = "data/exclude_labels.json"
    FURNITURE_LABEL_RULES_PATH: str = "data/furniture_search_label_rules_v1.json"
    FURNITURE_SEARCH_CANDIDATE_SCAN_LIMIT: int = 60
    FURNITURE_SEARCH_PER_MARKET_LIMIT: int = 3
    FURNITURE_VERIFIER_ENABLED: bool = True
    FURNITURE_VERIFIER_TOP_N_PER_MARKET: int = 3
    FURNITURE_VERIFIER_MODEL: str = "gpt-4.1-mini"
    FURNITURE_VERIFIER_FALLBACK_MODEL: str = "gpt-5-mini"
    FURNITURE_VERIFIER_TIMEOUT: int = 90
    FURNITURE_VERIFIER_MAX_OUTPUT_TOKENS: int = 5000
    FURNITURE_VERIFIER_TEXT_VERBOSITY: str = "medium"
    FURNITURE_VERIFIER_IMAGE_DETAIL: str = "low"
    FURNITURE_VERIFIER_IMAGE_FETCH_TIMEOUT: int = 20
    FURNITURE_VERIFIER_IMAGE_FETCH_ATTEMPTS: int = 3
    FURNITURE_VERIFIER_IMAGE_FETCH_CONCURRENCY: int = 8
    FURNITURE_VERIFIER_INPUT_PRICE_PER_MILLION: float | None = None
    FURNITURE_VERIFIER_OUTPUT_PRICE_PER_MILLION: float | None = None
    FURNITURE_VISION_VERIFIER_PROMPT_PATH: str = "prompts/gpt_furniture_vision_verifier_system_v1.md"
    FURNITURE_QUERY_TERMS_ENABLED: bool = True
    FURNITURE_QUERY_TERMS_MODEL: str = "gpt-4.1-mini"
    FURNITURE_QUERY_TERMS_FALLBACK_MODEL: str = "gpt-5-mini"
    FURNITURE_QUERY_TERMS_TIMEOUT: int = 90
    FURNITURE_QUERY_TERMS_MAX_OUTPUT_TOKENS: int = 5000
    FURNITURE_QUERY_TERMS_TEXT_VERBOSITY: str = "medium"
    FURNITURE_QUERY_TERMS_IMAGE_DETAIL: str = "low"
    FURNITURE_QUERY_TERMS_PROMPT_PATH: str = "prompts/gpt_furniture_query_terms_system_v1.md"
    FURNITURE_QUERY_TERMS_INPUT_PRICE_PER_MILLION: float | None = None
    FURNITURE_QUERY_TERMS_OUTPUT_PRICE_PER_MILLION: float | None = None
    FURNITURE_SEARCH_GLOBAL_TOP_K: int = 5
    FURNITURE_SEARCH_CROP_CONCURRENCY: int = 1
    FURNITURE_SEARCH_MARKET_CONCURRENCY: int = 1
    CROP_MASK_SHRINK_RATIO: float = 0.15
    CROP_MASK_TRANSPARENT: bool = False
    CROP_IMAGE_FORMAT: str = "JPEG"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True

    # Cost tracking (per call, USD)
    COST_VISION: float = 0.0015
    COST_SEARCHAPI: float = 0.0

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @model_validator(mode="after")
    def _validate_required(self) -> "Settings":
        mode = (self.APP_MODE or "").lower().strip()
        missing: list[str] = []

        def require(name: str, value: object) -> None:
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(name)

        if mode in {"polling", "webhook"}:
            require("TELEGRAM_TOKEN", self.TELEGRAM_TOKEN)

        if mode == "webhook":
            if not (self.CLOUD_TASKS_PROJECT_ID or self.VERTEX_PROJECT_ID):
                missing.append("CLOUD_TASKS_PROJECT_ID or VERTEX_PROJECT_ID")
            require("CLOUD_TASKS_LOCATION", self.CLOUD_TASKS_LOCATION)
            require("CLOUD_TASKS_QUEUE", self.CLOUD_TASKS_QUEUE)
            require("CLOUD_TASKS_WORKER_URL", self.CLOUD_TASKS_WORKER_URL)
            # request secret is recommended but optional

        if mode == "worker":
            require("OPENAI_API_KEY", self.OPENAI_API_KEY)
            require("SEARCHAPI_KEY", self.SEARCHAPI_KEY)
            require("GCS_BUCKET", self.GCS_BUCKET)
            require("CDN_URL_TEMPLATE", self.CDN_URL_TEMPLATE)
            require("DATABASE_URL", self.DATABASE_URL)
            require("VERTEX_PROJECT_ID", self.VERTEX_PROJECT_ID)

        if mode == "web":
            require("DATABASE_URL", self.DATABASE_URL)
            require("GCS_BUCKET", self.GCS_BUCKET)
            require("CDN_URL_TEMPLATE", self.CDN_URL_TEMPLATE)
            require("VERTEX_PROJECT_ID", self.VERTEX_PROJECT_ID)

        if missing:
            raise ValueError(f"Missing required settings for APP_MODE='{mode}': {', '.join(missing)}")

        return self

    @property
    def admin_chat_ids(self) -> set[int]:
        return {int(item.strip()) for item in self.ADMIN_CHAT_IDS.split(",") if item.strip()}

    @property
    def cloud_tasks_project_id(self) -> str:
        return self.CLOUD_TASKS_PROJECT_ID or self.VERTEX_PROJECT_ID

    @property
    def web_allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.WEB_ALLOWED_ORIGINS.split(",") if item.strip()]
