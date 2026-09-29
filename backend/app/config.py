"""全局配置 — pydantic-settings，支持 .env 与环境变量覆盖"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # mock=true：确定性模拟裁判（零依赖离线演示）；false：真实 LLM 裁判
    HALLU_MOCK: bool = True
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.deepseek.com/v1"
    JUDGE_MODEL: str = "deepseek-chat"
    JUDGE_TEMPERATURE: float = 0.0

    DATA_DIR: Path = PROJECT_ROOT / "data"
    RESULTS_DIR: Path = BACKEND_ROOT / "results"


settings = Settings()
