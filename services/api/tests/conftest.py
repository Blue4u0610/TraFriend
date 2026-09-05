import pytest
from fastapi.testclient import TestClient

from trafriend_api.main import create_app


@pytest.fixture()
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client

