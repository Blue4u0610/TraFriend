from sqlalchemy import Engine, create_engine


def create_database_engine(database_url: str) -> Engine:
    """Build the synchronous PostgreSQL engine used by API and capture paths."""

    if not database_url.startswith("postgresql+psycopg://"):
        raise ValueError("DATABASE_URL must use the postgresql+psycopg driver")
    return create_engine(database_url, pool_pre_ping=True)
