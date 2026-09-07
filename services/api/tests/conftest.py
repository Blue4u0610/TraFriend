import pytest
from fastapi.testclient import TestClient

from trafriend_api.main import create_app
from trafriend_api.settings import Settings


@pytest.fixture()
def client() -> TestClient:
    with TestClient(create_app(Settings())) as test_client:
        yield test_client
