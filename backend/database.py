import os
import psycopg2
import psycopg2.extras
from typing import Optional

DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")

_conn = None


def get_conn():
    global _conn
    if _conn is None or _conn.closed:
        if not DATABASE_URL:
            return None
        _conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        _conn.autocommit = True
    return _conn


def init_db() -> None:
    conn = get_conn()
    if conn is None:
        print("[DB] DATABASE_URL not set — skipping init")
        return
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS score_snapshots (
                id          SERIAL PRIMARY KEY,
                ticker      VARCHAR(10) NOT NULL,
                score       FLOAT NOT NULL,
                rsi         FLOAT,
                close       FLOAT,
                captured_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_ss_ticker ON score_snapshots(ticker);
            CREATE INDEX IF NOT EXISTS idx_ss_captured ON score_snapshots(captured_at);
        """)
    print("[DB] schema ready")


def save_snapshots(results: list) -> None:
    conn = get_conn()
    if conn is None:
        return
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO score_snapshots (ticker, score, rsi, close)
            VALUES %s
            """,
            [(r["ticker"], r["score"], r.get("rsi"), r.get("close")) for r in results],
        )


def get_score_history(ticker: str, limit: int = 90) -> list:
    conn = get_conn()
    if conn is None:
        return []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT score, rsi, close, captured_at
            FROM score_snapshots
            WHERE ticker = %s
            ORDER BY captured_at ASC
            LIMIT %s
            """,
            (ticker.upper(), limit),
        )
        return [dict(row) for row in cur.fetchall()]
