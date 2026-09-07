from sqlalchemy import Engine, create_engine


def normalize_database_url(database_url: str) -> str:
    """Select psycopg 3 for PostgreSQL URLs supplied by hosting platforms."""

    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    raise ValueError("DATABASE_URL must use a PostgreSQL URL")


def create_database_engine(database_url: str) -> Engine:
    """Build the synchronous PostgreSQL engine used by API and capture paths."""

    return create_engine(normalize_database_url(database_url), pool_pre_ping=True)
