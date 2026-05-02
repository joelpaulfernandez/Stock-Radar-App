import os
from typing import List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from signalradar import run_screener, DEFAULT_TICKERS, fetch_history, _session, _rate_limited_get
from database import (
    init_db, save_snapshots, get_score_history,
    get_watchlist, add_to_watchlist, remove_from_watchlist,
)

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
_TWELVE_BASE = "https://api.twelvedata.com"

app = FastAPI(
    title="SignalRadar API",
    description="Momentum & signal screener for stocks",
    version="0.4.0",
)

_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
_origins = ["*"] if _raw_origins == "*" else [o.strip() for o in _raw_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/signals")
def get_signals(
    tickers: Optional[str] = Query(None, description="Comma-separated tickers. Omit for default large caps."),
    days: int = Query(365, ge=60, le=2000),
    limit: int = Query(15, ge=1, le=100),
):
    tickers_list: List[str] = (
        [t.strip().upper() for t in tickers.split(",") if t.strip()]
        if tickers
        else DEFAULT_TICKERS
    )
    results = run_screener(tickers=tickers_list, days=days, limit=limit)
    if results:
        try:
            snapshot_ids = save_snapshots(results)
            if snapshot_ids:
                try:
                    from rag_agent import embed_and_store_snapshots
                    embed_and_store_snapshots(results, snapshot_ids)
                except Exception as e:
                    print(f"[RAG] embedding pipeline failed: {e}")
        except Exception as e:
            print(f"[DB] save_snapshots failed: {e}")
    return {"count": len(results), "tickers": tickers_list, "days": days, "limit": limit, "results": results}


@app.get("/watchlist")
def list_watchlist():
    items = get_watchlist()
    return {"watchlist": [{"ticker": r["ticker"], "added_at": r["added_at"].isoformat()} for r in items]}


@app.post("/watchlist/{ticker}", status_code=201)
def add_watchlist(ticker: str):
    added = add_to_watchlist(ticker)
    return {"ticker": ticker.upper(), "added": added}


@app.delete("/watchlist/{ticker}")
def delete_watchlist(ticker: str):
    removed = remove_from_watchlist(ticker)
    if not removed:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"{ticker.upper()} not in watchlist")
    return {"ticker": ticker.upper(), "removed": True}


@app.get("/history/{ticker}/scores")
def get_score_history_endpoint(
    ticker: str,
    limit: int = Query(90, ge=1, le=500),
):
    rows = get_score_history(ticker.upper(), limit)
    points = [
        {
            "date": row["captured_at"].strftime("%Y-%m-%d %H:%M"),
            "score": row["score"],
            "rsi": row["rsi"],
            "close": row["close"],
        }
        for row in rows
    ]
    return {"ticker": ticker.upper(), "points": points}


@app.get("/history/{ticker}")
def get_history(
    ticker: str,
    days: int = Query(120, ge=30, le=730),
):
    symbol = ticker.upper()
    try:
        resp = _rate_limited_get(
            f"{_TWELVE_BASE}/time_series",
            params={
                "symbol": symbol,
                "interval": "1day",
                "outputsize": min(days, 5000),
                "apikey": TWELVE_DATA_API_KEY,
            },
        )
        data = resp.json()
    except Exception as e:
        print(f"[WARN] history error for {symbol}: {e}")
        return {"ticker": symbol, "days": days, "points": []}

    if data.get("status") == "error" or "values" not in data:
        return {"ticker": symbol, "days": days, "points": []}

    values = sorted(data["values"], key=lambda x: x["datetime"])
    points = [{"date": v["datetime"][:10], "close": float(v["close"])} for v in values[-60:]]
    return {"ticker": symbol, "days": days, "points": points}


@app.get("/debug/{ticker}")
def debug_ticker(ticker: str):
    symbol = ticker.upper()
    try:
        resp = _session.get(
            f"{_TWELVE_BASE}/time_series",
            params={"symbol": symbol, "interval": "1day", "outputsize": 5, "apikey": TWELVE_DATA_API_KEY},
            timeout=15,
        )
        data = resp.json()
        return {"ticker": symbol, "status": data.get("status"), "message": data.get("message"),
                "has_values": "values" in data, "rows": len(data.get("values", [])),
                "sample": data.get("values", [])[:2], "api_key_set": bool(TWELVE_DATA_API_KEY)}
    except Exception as e:
        return {"ticker": symbol, "error": str(e)}


class RAGRequest(BaseModel):
    question: str


@app.post("/rag/query")
async def rag_query(body: RAGRequest):
    from fastapi import HTTPException
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    from rag_agent import run_agent
    answer = await run_agent(body.question.strip())
    return {"question": body.question, "answer": answer}


@app.get("/")
def root():
    return {
        "message": "Welcome to SignalRadar API",
        "endpoints": [
            "/signals", "/history/{ticker}", "/history/{ticker}/scores",
            "/watchlist", "/rag/query",
        ],
    }
