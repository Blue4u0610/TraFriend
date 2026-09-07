import pytest

from trafriend_api.infrastructure.persistence.database import normalize_database_url


@pytest.mark.parametrize(
    ("provided", "expected"),
    (
        (
            "postgresql+psycopg://app:secret@db/trafriend_prod",
            "postgresql+psycopg://app:secret@db/trafriend_prod",
        ),
        (
            "postgresql://app:secret@db/trafriend_prod",
            "postgresql+psycopg://app:secret@db/trafriend_prod",
        ),
        (
            "postgres://app:secret@db/trafriend_prod",
            "postgresql+psycopg://app:secret@db/trafriend_prod",
        ),
    ),
)
def test_normalize_database_url_selects_psycopg3(
    provided: str, expected: str
) -> None:
    assert normalize_database_url(provided) == expected


def test_normalize_database_url_rejects_non_postgresql_scheme() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        normalize_database_url("sqlite:///trafriend.db")
