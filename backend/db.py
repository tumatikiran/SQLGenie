import os

import pyodbc


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def build_connection_string() -> str:
    """Builds a safe, DSN-less connection string for SQL Server."""
    driver = os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")
    server = os.getenv("MSSQL_SERVER", "localhost")
    port = os.getenv("MSSQL_PORT", "1433")
    database = os.getenv("MSSQL_DATABASE")
    username = os.getenv("MSSQL_USERNAME")
    password = os.getenv("MSSQL_PASSWORD")

    if not database:
        raise RuntimeError("Missing required env var MSSQL_DATABASE")
    if not username:
        raise RuntimeError("Missing required env var MSSQL_USERNAME")
    if password is None:
        raise RuntimeError("Missing required env var MSSQL_PASSWORD")

    encrypt = _bool_env("MSSQL_ENCRYPT", default=False)
    trust_server_certificate = _bool_env("MSSQL_TRUST_SERVER_CERTIFICATE", default=True)

    # IMPORTANT: do not enable Trusted_Connection by default; enforce explicit read-only SQL user.
    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server},{port}",
        f"DATABASE={database}",
        f"UID={username}",
        f"PWD={password}",
        f"Encrypt={'yes' if encrypt else 'no'}",
        f"TrustServerCertificate={'yes' if trust_server_certificate else 'no'}",
        "Connection Timeout=5",
    ]
    return ";".join(parts) + ";"


def get_connection() -> pyodbc.Connection:
    """Creates a new pyodbc connection.

    Prefer short-lived connections (open per request) to avoid stale connections.
    """
    conn_str = build_connection_string()
    # autocommit=True is safe for SELECT-only workloads and avoids implicit transaction bloat.
    return pyodbc.connect(conn_str, autocommit=True)


def get_query_timeout_seconds(default: int = 30) -> int:
    v = os.getenv("MSSQL_QUERY_TIMEOUT_SECONDS")
    if not v:
        return default
    try:
        return max(1, int(v))
    except ValueError:
        return default
