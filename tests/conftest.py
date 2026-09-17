import pytest

from config import Settings


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        VERTEX_PROJECT_ID="test-project",
        GOOGLE_CLOUD_CREDENTIALS_PATH="gcloudcred.json",
        GCS_CREDENTIALS_PATH="gcloudcred.json",
        SEARCHAPI_KEY="x",
        TELEGRAM_TOKEN="x",
        GCS_BUCKET="bucket",
        CDN_URL_TEMPLATE="http://cdn/{key}",
    )
