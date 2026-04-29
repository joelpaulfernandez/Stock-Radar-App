import os
import math
import argparse
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd
import requests

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
_TWELVE_BASE = "https://api.twelvedata.com"

_session = requests.Session()
_session.headers.update({"User-Agent": "SignalRadar/1.0"})


# -----------------------------
# Helpers: indicators
# -----------------------------

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = pd.Series(np.where(delta > 0, delta, 0.0), index=close.index)
    loss = pd.Series(np.where(delta < 0, -delta, 0.0), index=close.index)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


# -----------------------------
# Data fetching
# -----------------------------

def fetch_history(ticker: str, days: int = 365) -> pd.DataFrame:
    outputsize = min(days, 5000)
    try:
        resp = _session.get(
            f"{_TWELVE_BASE}/time_series",
            params={
                "symbol": ticker,
                "interval": "1day",
                "outputsize": outputsize,
                "apikey": TWELVE_DATA_API_KEY,
            },
            timeout=15,
        )
        data = resp.json()
    except Exception as e:
        print(f"[WARN] Twelve Data request failed for {ticker}: {e}")
        return pd.DataFrame()

    if data.get("status") == "error" or "values" not in data:
        print(f"[WARN] Twelve Data error for {ticker}: {data.get('message', data)}")
        return pd.DataFrame()

    values = data["values"]
    if len(values) < 60:
        print(f"[WARN] Not enough rows for {ticker}: {len(values)}")
        return pd.DataFrame()

    df = pd.DataFrame(values)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").set_index("datetime")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])

    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA200"] = df["Close"].rolling(200).mean()
    df["RSI14"] = compute_rsi(df["Close"], 14)
    df["ATR14"] = compute_atr(df["High"], df["Low"], df["Close"], 14)
    df["ATR_PCT"] = df["ATR14"] / df["Close"]
    df["VolAvg20"] = df["Volume"].rolling(20).mean()
    df["VolRatio20"] = df["Volume"] / df["VolAvg20"]
    df["RET_5D"] = df["Close"].pct_change(5)
    df["RET_20D"] = df["Close"].pct_change(20)
    df.dropna(inplace=True)
    return df


# -----------------------------
# Signal score
# -----------------------------

def compute_signal_score(row: pd.Series) -> Dict[str, Any]:
    score = 0.0
    tags: List[str] = []
    notes: List[str] = []

    close = row["Close"]
    ma50 = row["MA50"]
    ma200 = row["MA200"]
    rsi = row["RSI14"]
    vol_ratio = row["VolRatio20"]
    atr_pct = row["ATR_PCT"]

    if not math.isnan(ma50) and not math.isnan(ma200):
        if close > ma50:
            score += 15
            tags.append("Above MA50")
        else:
            score -= 10
        if close > ma200:
            score += 15
            tags.append("Above MA200")
        else:
            score -= 10
        if close > ma50 > ma200:
            score += 10
            tags.append("Strong Uptrend")

    if not math.isnan(rsi):
        if 50 <= rsi <= 70:
            score += 20
            tags.append("Bullish Momentum")
        elif 40 <= rsi < 50:
            score += 10
            tags.append("Building Momentum")
        elif rsi > 75:
            score -= 10
            tags.append("Overbought")
        elif rsi < 30:
            score -= 15
            tags.append("Oversold")

    ret_5d = row.get("RET_5D", np.nan)
    ret_20d = row.get("RET_20D", np.nan)
    if not math.isnan(ret_5d):
        score += max(min(ret_5d * 100, 10), -10)
    if not math.isnan(ret_20d):
        score += max(min(ret_20d * 50, 15), -15)

    if not math.isnan(vol_ratio):
        if vol_ratio > 1.5:
            score += 10
            tags.append("High Volume")
        elif vol_ratio < 0.7:
            score -= 5
            tags.append("Low Volume")

    if not math.isnan(atr_pct):
        if 0.015 <= atr_pct <= 0.05:
            score += 10
            tags.append("Tradable Volatility")
        elif atr_pct > 0.08:
            score -= 10
            tags.append("Very Volatile")
        elif atr_pct < 0.01:
            score -= 5
            tags.append("Very Quiet")

    notes.append(f"RSI={rsi:.1f}" if not math.isnan(rsi) else "RSI=n/a")
    notes.append(f"Vol xAvg={vol_ratio:.2f}" if not math.isnan(vol_ratio) else "Vol xAvg=n/a")
    notes.append(f"ATR%={atr_pct*100:.2f}%" if not math.isnan(atr_pct) else "ATR%=n/a")

    return {"score": round(score, 1), "tags": tags, "notes": "; ".join(notes)}


# -----------------------------
# Screener
# -----------------------------

DEFAULT_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    "NFLX", "ADBE", "CRM", "INTC", "CSCO", "ORCL", "IBM",
    "JPM", "BAC", "WFC", "GS", "MS", "V", "MA",
    "XOM", "CVX", "COP",
    "UNH", "JNJ", "PFE", "ABBV", "LLY", "MRK",
    "KO", "PEP", "MCD", "COST", "WMT", "HD", "NKE",
    "DIS", "CMCSA", "T", "VZ",
]


def analyze_ticker(ticker: str, days: int = 365) -> Optional[Dict[str, Any]]:
    try:
        df = fetch_history(ticker, days)
        if df.empty:
            return None
        last = df.iloc[-1]
        sig = compute_signal_score(last)
        return {
            "ticker": ticker,
            "close": float(last["Close"]),
            "rsi": float(last["RSI14"]),
            "vol_ratio": float(last["VolRatio20"]),
            "atr_pct": float(last["ATR_PCT"]),
            "ret_5d": float(last["RET_5D"]),
            "ret_20d": float(last["RET_20D"]),
            "score": sig["score"],
            "tags": sig["tags"],
            "notes": sig["notes"],
        }
    except Exception as e:
        print(f"[WARN] Failed for {ticker}: {e}")
        return None


def run_screener(tickers: List[str], days: int = 365, limit: int = 15) -> List[Dict[str, Any]]:
    results = []
    for t in tickers:
        print(f"Analyzing {t} ...")
        res = analyze_ticker(t, days)
        if res is not None:
            results.append(res)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


# -----------------------------
# CLI
# -----------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SignalRadar momentum screener")
    parser.add_argument("--tickers", type=str, default=None)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--limit", type=int, default=15)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else DEFAULT_TICKERS
    results = run_screener(tickers=tickers, days=args.days, limit=args.limit)
    if not results:
        print("No results.")
        return
    print(f"\n=== Top {len(results)} Signals ===")
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['ticker']} score={r['score']} rsi={r['rsi']:.1f} tags={r['tags']}")


if __name__ == "__main__":
    main()
