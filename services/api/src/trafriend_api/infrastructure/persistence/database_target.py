from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sqlalchemy.engine import make_url

from trafriend_api.infrastructure.persistence.database import normalize_database_url

LOCAL_DATABASE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class DatabaseEnvironment(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    PRODUCTION = "PRODUCTION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DatabaseTarget:
    """Non-secret database identity safe for operational logs."""

    environment: DatabaseEnvironment
    host: str
    port: int
    database: str


def identify_database_target(database_url: str, configured_environment: str) -> DatabaseTarget:
    """Classify an inherited DATABASE_URL without retaining credentials."""

    url = make_url(normalize_database_url(database_url))
    host = (url.host or "UNKNOWN").strip().lower()
    database = (url.database or "UNKNOWN").strip()
    environment = configured_environment.strip().lower()
    is_local = host in LOCAL_DATABASE_HOSTS

    if environment == "production" and not is_local and database != "UNKNOWN":
        classification = DatabaseEnvironment.PRODUCTION
    elif environment == "development" and is_local and database == "trafriend_dev":
        classification = DatabaseEnvironment.DEVELOPMENT
    else:
        classification = DatabaseEnvironment.UNKNOWN

    return DatabaseTarget(
        environment=classification,
        host=host,
        port=url.port or 5432,
        database=database,
    )


def require_writable_database_target(
    database_url: str, configured_environment: str
) -> DatabaseTarget:
    """Reject ambiguous or environment-mismatched data-writing targets."""

    target = identify_database_target(database_url, configured_environment)
    if target.environment == DatabaseEnvironment.UNKNOWN:
        raise ValueError("DATABASE_URL target does not match TRAFRIEND_ENV")
    return target
