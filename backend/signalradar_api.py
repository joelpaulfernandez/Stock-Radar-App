from typing import List, Optional
import yfinance as yf

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# Import your core logic from signalradar.py
from signalradar import run_screener, DEFAULT_TICKERS, fetch_history

app = FastAPI(
    title="SignalRadar API",
    description="Momentum & signal screener for stocks",
    version="0.1.0",
)

# Allow frontend apps (e.g., Next.js) to call this API from localhost later
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # you can lock this down later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/signals")
def get_signals(
    tickers: Optional[str] = Query(
        None,
        description="Comma-separated list of tickers. If omitted, uses default large caps.",
        example="AAPL,MSFT,NVDA,TSLA",
    ),
    days: int = Query(
        365,
        ge=60,
        le=2000,
        description="Number of days of history to use (must be >= 60 for indicators).",
    ),
    limit: int = Query(
        15,
        ge=1,
        le=100,
        description="How many top signals to return.",
    ),
):
    """
    Returns top momentum / signal stocks based on your scoring engine.
    """

    # Use provided tickers or fall back to default large caps
    if tickers:
        tickers_list: List[str] = [
            t.strip().upper() for t in tickers.split(",") if t.strip()
        ]
    else:
        tickers_list = DEFAULT_TICKERS

    results = run_screener(
        tickers=tickers_list,
        days=days,
        limit=limit,
    )

    return {
        "count": len(results),
        "tickers": tickers_list,
        "days": days,
        "limit": limit,
        "results": results,
    }


@app.get("/history/{ticker}")
def get_history(
    ticker: str,
    days: int = Query(
        120,
        ge=30,
        le=730,
        description="Number of days of history to return for this ticker.",
    ),
):
    """
    Return recent daily close prices for a single ticker,
    for use in charts / sparklines.

    Uses a lightweight yfinance history call instead of fetch_history,
    so it does not depend on indicator columns or 200-day lookback.
    """
    symbol = ticker.upper()
    try:
        t = yf.Ticker(symbol)
        df = t.history(
            period=f"{days}d",
            interval="1d",
            auto_adjust=False,
        )
    except Exception as e:
        print(f"[WARN] history error for {symbol}: {e}")
        return {
            "ticker": symbol,
            "days": days,
            "points": [],
        }

    if df.empty:
        return {
            "ticker": symbol,
            "days": days,
            "points": [],
        }

    # Keep only rows with a closing price
    df = df.dropna(subset=["Close"])

    # Take at most the last 60 points for the chart
    df_tail = df.tail(60)

    points = [
        {
            "date": idx.strftime("%Y-%m-%d"),
            "close": float(row["Close"]),
        }
        for idx, row in df_tail.iterrows()
    ]

    return {
        "ticker": symbol,
        "days": days,
        "points": points,
    }


@app.get("/")
def root():
    return {
        "message": "Welcome to SignalRadar API",
        "endpoints": ["/signals"],
    }