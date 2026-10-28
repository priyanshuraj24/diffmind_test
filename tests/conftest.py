import pytest

from diffmind.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database_url="postgresql://diffmind:local-test-only@127.0.0.1:16433/diffmind_test",
                    webhook_secret="test-secret", internal_token="test-internal", deepseek_api_key="test-model-key",
                    github_app_id=123, github_private_key=tmp_path / "key.pem", data_dir=tmp_path,
                    qdrant_url="http://127.0.0.1:16434", worker_enabled=False)
