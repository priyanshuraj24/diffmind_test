from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DIFFMIND_", env_file=".env", extra="ignore")
    database_url: SecretStr
    webhook_secret: SecretStr
    internal_token: SecretStr
    deepseek_api_key: SecretStr
    github_app_id: int
    github_private_key: Path
    allowed_repos: str = "priyanshuraj24/diffmind_test"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: SecretStr = SecretStr("")
    collection: str = "diffmind_code_v1"
    data_dir: Path = Path("/data")
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    deepseek_model: str = "deepseek-flash"
    deepseek_url: str = "https://api.deepseek.com"
    debounce_seconds: int = 30
    lease_seconds: int = 1800
    max_files: int = 20000
    max_file_bytes: int = 250000
    max_source_bytes: int = 50000000
    max_chunks: int = 100000
    batch_chars: int = 40000
    max_batches: int = 12
    max_findings: int = 5
    publish: bool = False
    worker_enabled: bool = True
    retention_days: int = 14

    def allows(self, repo: str) -> bool:
        return repo.lower() in {r.strip().lower() for r in self.allowed_repos.split(",") if r.strip()}
