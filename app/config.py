import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    erpnext_base_url: str = os.getenv("ERPNEXT_BASE_URL", "http://site1.localhost:8080")
    erpnext_api_key: str = os.getenv("ERPNEXT_API_KEY", "")
    erpnext_api_secret: str = os.getenv("ERPNEXT_API_SECRET", "")
    erpnext_company: str = os.getenv("ERPNEXT_COMPANY", "")
    default_warehouse_alias: str = os.getenv("DEFAULT_WAREHOUSE_ALIAS", "南宁仓")
    snapshot_dir: str = os.getenv("SNAPSHOT_DIR", "data/snapshots")
    master_data_dir: str = os.getenv("MASTER_DATA_DIR", "data/master_data")
    master_data_cache_db: str = os.getenv("MASTER_DATA_CACHE_DB", "data/master_data_cache.sqlite3")
    enable_llm_extractor: bool = os.getenv("ENABLE_LLM_EXTRACTOR", "false").lower() == "true"
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai_compatible")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "qwen2.5:7b")
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "20"))


settings = Settings()
