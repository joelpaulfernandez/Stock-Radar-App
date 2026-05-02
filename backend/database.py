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
        try:
            from pgvector.psycopg2 import register_vector
            register_vector(_conn)
        except Exception:
            pass
    return _conn


def init_db() -> None:
    conn = get_conn()
    if conn is None:
        print("[DB] DATABASE_URL not set — skipping init")
        return
    with conn.cursor() as cur:
        cur.execute("""
            CREATE EXTENSION IF NOT EXISTS vector;

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

            ALTER TABLE score_snapshots
                ADD COLUMN IF NOT EXISTS vol_ratio FLOAT,
                ADD COLUMN IF NOT EXISTS atr_pct FLOAT,
                ADD COLUMN IF NOT EXISTS ret_5d FLOAT,
                ADD COLUMN IF NOT EXISTS ret_20d FLOAT,
                ADD COLUMN IF NOT EXISTS tags TEXT[],
                ADD COLUMN IF NOT EXISTS embedding_text TEXT,
                ADD COLUMN IF NOT EXISTS embedding vector(384);

            CREATE TABLE IF NOT EXISTS watchlist (
                ticker     VARCHAR(10) PRIMARY KEY,
                added_at   TIMESTAMPTZ DEFAULT NOW()
            );
        """)
    print("[DB] schema ready")


def save_snapshots(results: list) -> list:
    """Insert snapshots, return list of (id, ticker) tuples."""
    conn = get_conn()
    if conn is None:
        return []
    with conn.cursor() as cur:
        rows = psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO score_snapshots
                (ticker, score, rsi, close, vol_ratio, atr_pct, ret_5d, ret_20d, tags)
            VALUES %s
            RETURNING id, ticker
            """,
            [
                (
                    r["ticker"], r["score"], r.get("rsi"), r.get("close"),
                    r.get("vol_ratio"), r.get("atr_pct"),
                    r.get("ret_5d"), r.get("ret_20d"),
                    r.get("tags", []),
                )
                for r in results
            ],
            fetch=True,
        )
        return rows  # [(id, ticker), ...]


def update_snapshot_embedding(snapshot_id: int, embedding_text: str, embedding: list) -> None:
    conn = get_conn()
    if conn is None:
        return
    import numpy as np
    vec = np.array(embedding, dtype=np.float32)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE score_snapshots SET embedding_text = %s, embedding = %s WHERE id = %s",
            (embedding_text, vec, snapshot_id),
        )


def semantic_search(query_embedding, top_k: int = 5) -> list:
    conn = get_conn()
    if conn is None:
        return []
    import numpy as np
    vec = np.array(query_embedding, dtype=np.float32)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT ticker, score, rsi, close, vol_ratio, atr_pct,
                   ret_5d, ret_20d, tags, embedding_text, captured_at,
                   1 - (embedding <=> %s) AS similarity
            FROM score_snapshots
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (vec, vec, top_k),
        )
        return [dict(row) for row in cur.fetchall()]


def get_watchlist() -> list:
    conn = get_conn()
    if conn is None:
        return []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT ticker, added_at FROM watchlist ORDER BY added_at DESC")
        return [dict(row) for row in cur.fetchall()]


def add_to_watchlist(ticker: str) -> bool:
    conn = get_conn()
    if conn is None:
        return False
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO watchlist (ticker) VALUES (%s) ON CONFLICT (ticker) DO NOTHING",
            (ticker.upper(),),
        )
        return cur.rowcount > 0


def remove_from_watchlist(ticker: str) -> bool:
    conn = get_conn()
    if conn is None:
        return False
    with conn.cursor() as cur:
        cur.execute("DELETE FROM watchlist WHERE ticker = %s", (ticker.upper(),))
        return cur.rowcount > 0


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
