

# Stock Radar (SignalRadar)

**Stock Radar** (code name: **SignalRadar**) is a full-stack stock screener that surfaces high-momentum, technically strong tickers from a universe of large-cap stocks.

-  **Python + FastAPI backend** that fetches market data and computes a composite score
-  **Next.js frontend** with a dark, dashboard-style UI
-  Interactive per-ticker charts using Chart.js
-  Filters for score, RSI, and trend tags (Bullish Momentum, Strong Uptrend, etc.)

---

## Project Structure

```bash
Stock-Radar-App/
├── backend/        # FastAPI + yfinance + pandas
└── frontend/       # Next.js + Tailwind + Chart.js
```

---

## Backend Setup (FastAPI)

Requirements: **Python 3.9+**

From the repo root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt

# Run the API (development)
python3 -m uvicorn signalradar_api:app --reload
```

The API will be available at:

- Docs: http://127.0.0.1:8000/docs  
- Signals: http://127.0.0.1:8000/signals  
- History: http://127.0.0.1:8000/history/AAPL  

---

## Frontend Setup (Next.js)

Requirements: **Node 18+**

From the repo root:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at:  
👉 http://localhost:3000

By default the frontend expects the backend at `http://127.0.0.1:8000`.

If you host the backend elsewhere, create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
```

---

## What the Screener Does (High Level)

The backend:

- Uses **yfinance** to download daily OHLCV data for a universe of tickers.
- Computes:
  - Moving averages (50-day, 200-day)
  - RSI
  - ATR% (volatility)
  - Volume vs. average volume
  - 5-day and 20-day returns
- Assigns a **composite score** per ticker.
- Adds descriptive **tags**, such as:
  - `Above MA50`, `Above MA200`
  - `Strong Uptrend`, `Bullish Momentum`
  - `Overbought`
  - `Low Volume`, `Tradable Volatility`

The frontend:

- Calls `/signals` to get a ranked list.
- Lets you filter by **min score**, **RSI range**, **Bullish Momentum**, **Strong Uptrend**.
- Opens a modal with a **price history chart** for each ticker using `/history/{ticker}`.

---

## Ideas for Future Work

- Deploy backend to Render / Railway / Fly.io
- Deploy frontend to Vercel
- Add sector / industry filters
- Add watchlists and saved screens
- Export screener results as CSV

---