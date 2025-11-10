# Stock Radar Frontend (Next.js)

This is the frontend for **Stock Radar / SignalRadar**, a momentum and signal screener for stocks.

- Built with **Next.js (App Router)** and **React**
- Styled with **Tailwind CSS**
- Uses **Chart.js** for per-ticker price charts
- Connects to a FastAPI backend for signal and history data

---

## Getting Started

From the repo root:

```bash
cd frontend
npm install
npm run dev
```

Then open your browser at:  
👉 http://localhost:3000

Make sure your backend (FastAPI) server is running at http://127.0.0.1:8000 before starting.

---

## Configuration

If your backend runs on a different URL, create a file named `.env.local` in the `frontend/` folder:

```env
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
```

---

## Key Features

- **Signal Screener Dashboard**  
  Displays top-ranked tickers with technical indicators and tags (Bullish Momentum, Strong Uptrend, etc.)

- **Custom Filters**  
  Adjust minimum score, RSI range, and filter by trend.

- **Interactive Charts**  
  View recent price history for each ticker in a modal window.

- **Custom Ticker Universe**  
  Paste any set of tickers (comma or space-separated) to analyze your own list.

---

## Project Structure

```bash
frontend/
├── src/app/
│   ├── page.js        # Main dashboard UI
│   ├── layout.js      # Root layout
│   ├── globals.css    # Global styles
│   └── favicon.ico
├── public/            # Static assets (logos, icons)
├── package.json       # Dependencies
├── next.config.mjs    # Next.js configuration
├── postcss.config.mjs # PostCSS / Tailwind config
├── eslint.config.mjs  # ESLint configuration
└── .gitignore
```

---

## Tech Stack

- **Framework:** Next.js 14 (React)
- **Styling:** Tailwind CSS
- **Charts:** Chart.js / react-chartjs-2
- **Language:** JavaScript (ES6+)

---

## Commands

```bash
npm run dev      # Start development server
npm run build    # Build for production
npm run start    # Start production build
npm run lint     # Run ESLint checks
```

---
