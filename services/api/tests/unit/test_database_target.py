import pytest

from trafriend_api.infrastructure.persistence.database_target import (
    DatabaseEnvironment,
    identify_database_target,
    require_writable_database_target,
)


def test_local_trafriend_database_is_explicitly_development() -> None:
    target = require_writable_database_target(
        "postgresql://local-user:local-secret@localhost:5432/trafriend_dev",
        "development",
    )

    assert target.environment == DatabaseEnvironment.DEVELOPMENT
    assert (target.host, target.port, target.database) == (
        "localhost",
        5432,
        "trafriend_dev",
    )
    assert "local-user" not in repr(target)
    assert "local-secret" not in repr(target)


def test_remote_database_is_production_only_when_explicitly_configured() -> None:
    target = require_writable_database_target(
        "postgresql://render-user:render-secret@dpg-example.internal/prod_db",
        "production",
    )

    assert target.environment == DatabaseEnvironment.PRODUCTION
    assert target.host == "dpg-example.internal"
    assert target.database == "prod_db"
    assert "render-user" not in repr(target)
    assert "render-secret" not in repr(target)


@pytest.mark.parametrize(
    ("url", "environment"),
    (
        ("postgresql://user:secret@localhost/trafriend_dev", "production"),
        ("postgresql://user:secret@dpg-example.internal/prod_db", "development"),
        ("postgresql://user:secret@localhost/another_database", "development"),
        ("postgresql://user:secret@dpg-example.internal/prod_db", "staging"),
    ),
)
def test_ambiguous_or_mismatched_write_target_is_rejected(
    url: str, environment: str
) -> None:
    assert identify_database_target(url, environment).environment == DatabaseEnvironment.UNKNOWN
    with pytest.raises(ValueError, match="does not match"):
        require_writable_database_target(url, environment)
