import pandas as pd
import numpy as np
import yfinance as yf

def fetch_history(ticker: str, days: int = 180) -> pd.DataFrame:
    """
    Fetch daily OHLCV history for a single ticker.

    Uses Ticker().history() instead of yf.download() to avoid MultiIndex
    column issues some yfinance versions have.
    """
    # Use Ticker().history to get a single-symbol DataFrame
    try:
        t = yf.Ticker(ticker)
        df = t.history(
            period=f"{days}d",
            interval="1d",
            auto_adjust=False
        )
    except Exception as e:
        print(f"[WARN] yfinance error for {ticker}: {e}")
        return pd.DataFrame()

    if df.empty or len(df) < 60:
        # not enough data to compute indicators
        return pd.DataFrame()

    # Ensure we have the expected columns
    required_cols = {"Close", "High", "Low", "Volume"}
    if not required_cols.issubset(set(df.columns)):
        print(f"[WARN] Unexpected columns for {ticker}: {list(df.columns)}")
        return pd.DataFrame()

    # Drop rows with missing core fields
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])

    # Indicators
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
#!/usr/bin/env python3
"""
SignalRadar - Phase 1
Simple momentum & signal screener for a list of stocks.

Usage:
    python3 signalradar.py            # uses default tickers, prints top 15
    python3 signalradar.py --limit 20 --days 180
"""

import argparse
import math
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd
import yfinance as yf


# -----------------------------
# Helpers: indicators
# -----------------------------

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    gain = pd.Series(gain, index=close.index)
    loss = pd.Series(loss, index=close.index)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=period).mean()
    return atr


# -----------------------------
# Signal score
# -----------------------------

def compute_signal_score(row: pd.Series) -> Dict[str, Any]:
    """
    Given the latest row with indicators, compute a score & tags.
    """
    score = 0.0
    tags: List[str] = []
    notes: List[str] = []

    close = row["Close"]
    ma20 = row["MA20"]
    ma50 = row["MA50"]
    ma200 = row["MA200"]
    rsi = row["RSI14"]
    vol_ratio = row["VolRatio20"]
    atr_pct = row["ATR_PCT"]

    # --- Trend (uptrend / downtrend) ---
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

    # --- Momentum via RSI ---
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

    # --- Recent returns (5-day & 20-day) ---
    ret_5d = row.get("RET_5D", np.nan)
    ret_20d = row.get("RET_20D", np.nan)

    if not math.isnan(ret_5d):
        score += max(min(ret_5d * 100, 10), -10)  # clamp between -10 and +10
    if not math.isnan(ret_20d):
        score += max(min(ret_20d * 50, 15), -15)  # clamp between -15 and +15

    # --- Volume & volatility ---
    if not math.isnan(vol_ratio):
        if vol_ratio > 1.5:
            score += 10
            tags.append("High Volume")
        elif vol_ratio < 0.7:
            score -= 5
            tags.append("Low Volume")

    if not math.isnan(atr_pct):
        # prefer moderate volatility
        if 0.015 <= atr_pct <= 0.05:  # 1.5%–5% daily ATR
            score += 10
            tags.append("Tradable Volatility")
        elif atr_pct > 0.08:
            score -= 10
            tags.append("Very Volatile")
        elif atr_pct < 0.01:
            score -= 5
            tags.append("Very Quiet")

    # Notes for explanation
    notes.append(f"RSI={rsi:.1f}" if not math.isnan(rsi) else "RSI=n/a")
    notes.append(f"Vol xAvg={vol_ratio:.2f}" if not math.isnan(vol_ratio) else "Vol xAvg=n/a")
    notes.append(f"ATR%={atr_pct*100:.2f}%" if not math.isnan(atr_pct) else "ATR%=n/a")

    return {
        "score": round(score, 1),
        "tags": tags,
        "notes": "; ".join(notes)
    }


# -----------------------------
# Data fetching & processing
# -----------------------------

DEFAULT_TICKERS = [
    # Mega-cap tech / growth
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA",
    "NFLX", "ADBE", "CRM", "INTC", "CSCO", "ORCL", "IBM",
    # Financials
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "V", "MA", "PYPL",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG",
    # Healthcare
    "UNH", "JNJ", "PFE", "ABBV", "LLY", "MRK", "TMO",
    # Consumer / retail
    "KO", "PEP", "MCD", "SBUX", "COST", "WMT", "TGT", "HD", "LOW", "NKE",
    # Communications / media
    "DIS", "CMCSA", "T", "VZ",
]

def fetch_history(ticker: str, days: int = 180) -> pd.DataFrame:
    """
    Fetch daily OHLCV history for a single ticker.

    Uses Ticker().history() instead of yf.download() to avoid MultiIndex
    column issues some yfinance versions have.
    """
    try:
        t = yf.Ticker(ticker)
        df = t.history(
            period=f"{days}d",
            interval="1d",
            auto_adjust=False
        )
    except Exception as e:
        print(f"[WARN] yfinance error for {ticker}: {e}")
        return pd.DataFrame()

    if df.empty:
        print(f"[WARN] No data for {ticker}")
        return pd.DataFrame()

    if len(df) < 60:
        # not enough data to compute indicators
        print(f"[WARN] Not enough rows for {ticker}: {len(df)}")
        return pd.DataFrame()

    required_cols = {"Close", "High", "Low", "Volume"}
    if not required_cols.issubset(set(df.columns)):
        print(f"[WARN] Unexpected columns for {ticker}: {list(df.columns)}")
        return pd.DataFrame()

    # Drop rows with missing core fields
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])

    # Indicators
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


def analyze_ticker(ticker: str, days: int = 180) -> Optional[Dict[str, Any]]:
    try:
        df = fetch_history(ticker, days)
        if df.empty:
            return None

        last = df.iloc[-1]
        sig = compute_signal_score(last)

        result = {
            "ticker": ticker,
            "close": float(last["Close"]),
            "rsi": float(last["RSI14"]),
            "vol_ratio": float(last["VolRatio20"]),
            "atr_pct": float(last["ATR_PCT"]),
            "ret_5d": float(last["RET_5D"]),
            "ret_20d": float(last["RET_20D"]),
            "score": sig["score"],
            "tags": sig["tags"],
            "notes": sig["notes"]
        }
        return result
    except Exception as e:
        print(f"[WARN] Failed for {ticker}: {e}")
        return None


def run_screener(
    tickers: List[str],
    days: int = 180,
    limit: int = 15
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    for t in tickers:
        print(f"Analyzing {t} ...")
        res = analyze_ticker(t, days)
        if res is not None:
            results.append(res)

    # sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def print_results(results: List[Dict[str, Any]]) -> None:
    if not results:
        print("No results.")
        return

    print("\n=== Top Signals ===")
    header = f"{'Rank':<4} {'Ticker':<6} {'Score':>6} {'Price':>10} {'RSI':>6} {'VolxAvg':>8} {'ATR%':>8} {'5d%':>8} {'20d%':>8}  Tags"
    print(header)
    print("-" * len(header))

    for i, r in enumerate(results, start=1):
        atr_pct = r['atr_pct'] * 100
        ret_5d_pct = r['ret_5d'] * 100
        ret_20d_pct = r['ret_20d'] * 100
        tags_str = ",".join(r["tags"]) if r["tags"] else "-"

        line = (
            f"{i:<4} "
            f"{r['ticker']:<6} "
            f"{r['score']:>6.1f} "
            f"{r['close']:>10.2f} "
            f"{r['rsi']:>6.1f} "
            f"{r['vol_ratio']:>8.2f} "
            f"{atr_pct:>8.2f} "
            f"{ret_5d_pct:>8.2f} "
            f"{ret_20d_pct:>8.2f}  "
            f"{tags_str}"
        )
        print(line)

    print("\n(Score is a composite of trend, RSI, recent returns, volume, and volatility.)")


# -----------------------------
# CLI
# -----------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SignalRadar momentum screener")
    parser.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated tickers (default: built-in large caps)",
        default=None
    )
    parser.add_argument(
        "--days",
        type=int,
        help="Number of days of history to use (default: 180)",
        default=180
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="How many top signals to show (default: 15)",
        default=15
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = DEFAULT_TICKERS

    results = run_screener(
        tickers=tickers,
        days=args.days,
        limit=args.limit
    )
    print_results(results)


if __name__ == "__main__":
    main()