from functools import lru_cache
from pathlib import Path

from pydantic import BaseSettings, Field

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    """Application level configuration."""

    database_url: str = Field("sqlite:///./planner.db", env="PLANNER_DATABASE_URL")
    planner_api_prefix: str = Field("/api", env="PLANNER_API_PREFIX")
    csv_import_chunk_size: int = Field(500, env="PLANNER_IMPORT_CHUNK_SIZE")
    executor_base_url: str = Field("http://localhost:9100", env="EXECUTOR_BASE_URL")
    executor_api_key: str | None = Field(None, env="EXECUTOR_API_KEY")
    executor_callback_secret: str = Field("executor-secret", env="EXECUTOR_CALLBACK_SECRET")
    benchmark_api_base_url: str = Field("http://localhost:9200", env="BENCHMARK_API_BASE_URL")
    benchmark_api_key: str | None = Field(None, env="BENCHMARK_API_KEY")
    benchmark_cache_ttl_seconds: int = Field(300, env="BENCHMARK_CACHE_TTL_SECONDS")
    benchmark_fail_open: bool = Field(True, env="BENCHMARK_FAIL_OPEN")
    message_bus_broker: str | None = Field(None, env="MESSAGE_BUS_BROKER")
    message_bus_topic: str = Field("planner.events", env="MESSAGE_BUS_TOPIC")
    message_bus_max_retries: int = Field(3, env="MESSAGE_BUS_MAX_RETRIES")
    message_bus_publish_timeout: float = Field(5.0, env="MESSAGE_BUS_PUBLISH_TIMEOUT")
    metrics_enabled: bool = Field(True, env="PLANNER_METRICS_ENABLED")
    feature_flag_mock_integrations: bool = Field(False, env="PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS")
    redis_url: str | None = Field(None, env="PLANNER_REDIS_URL")
    executor_callback_url: str = Field("http://localhost:8000/api/planner/executor/callback", env="EXECUTOR_CALLBACK_URL")
    yida_materials_config_path: str = Field(
        default=str(BASE_DIR / "backend" / "config" / "yida_materials.json"),
        env="YIDA_MATERIALS_CONFIG_PATH",
    )
    yida_processes_config_path: str = Field(
        default=str(BASE_DIR / "backend" / "config" / "yida_processes.json"),
        env="YIDA_PROCESSES_CONFIG_PATH",
    )

    # Media storage (material images)
    planner_media_dir: str = Field(
        default=str(BASE_DIR / "backend" / "media"),
        env="PLANNER_MEDIA_DIR",
    )
    planner_persist_material_images: bool = Field(
        default=True,
        env="PLANNER_PERSIST_MATERIAL_IMAGES",
    )

    # Admin key (very lightweight protection for admin-only maintenance endpoints).
    # If set, mutating endpoints guarded by `require_admin_key` will require header:
    #   X-PLANNER-ADMIN-KEY: <value>
    planner_admin_key: str | None = Field(default=None, env="PLANNER_ADMIN_KEY")

    # ===== Optional LLM (e.g. 百炼/通义等) integration =====
    # We use an OpenAI-compatible endpoint by default:
    #   POST {base_url}/v1/chat/completions
    llm_provider: str = Field(default="openai_compatible", env="PLANNER_LLM_PROVIDER")
    llm_base_url: str | None = Field(default=None, env="PLANNER_LLM_BASE_URL")
    llm_api_key: str | None = Field(default=None, env="PLANNER_LLM_API_KEY")
    llm_model: str = Field(default="qwen-plus", env="PLANNER_LLM_MODEL")
    llm_timeout_seconds: float = Field(default=20.0, env="PLANNER_LLM_TIMEOUT_SECONDS")

    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()


settings = get_settings()
