import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    erpnext_base_url: str = os.getenv("ERPNEXT_BASE_URL", "http://site1.localhost:8080")
    erpnext_api_key: str = os.getenv("ERPNEXT_API_KEY", "")
    erpnext_api_secret: str = os.getenv("ERPNEXT_API_SECRET", "")
    default_warehouse_alias: str = os.getenv("DEFAULT_WAREHOUSE_ALIAS", "南宁仓")
    snapshot_dir: str = os.getenv("SNAPSHOT_DIR", "data/snapshots")
    master_data_dir: str = os.getenv("MASTER_DATA_DIR", "data/master_data")
    enable_llm_extractor: bool = os.getenv("ENABLE_LLM_EXTRACTOR", "false").lower() == "true"


settings = Settings()
