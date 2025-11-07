"use client";

import { useEffect, useState } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend
);

const API_BASE = "http://127.0.0.1:8000";

export default function Home() {
  const [data, setData] = useState(null);
  const [limit, setLimit] = useState(15);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  // filters
  const [minScore, setMinScore] = useState(0);
  const [rsiMin, setRsiMin] = useState(0);
  const [rsiMax, setRsiMax] = useState(100);
  const [requireBullish, setRequireBullish] = useState(false);
  const [requireUptrend, setRequireUptrend] = useState(false);

  // chart modal state
  const [selectedTicker, setSelectedTicker] = useState(null);
  const [history, setHistory] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [tickersText, setTickersText] = useState("");

  useEffect(() => {
    async function fetchSignals() {
      try {
        setLoading(true);
        setError("");
        let url = `${API_BASE}/signals?limit=${limit}`;

        if (tickersText.trim()) {
          const normalized = tickersText
            .split(/[,\s]+/)
            .map((t) => t.trim().toUpperCase())
            .filter(Boolean)
            .join(",");
          url += `&tickers=${encodeURIComponent(normalized)}`;
        }

        const res = await fetch(url);
        if (!res.ok) {
          throw new Error(`API error: ${res.status}`);
        }
        const json = await res.json();
        setData(json);
      } catch (err) {
        console.error(err);
        setError(err.message || "Failed to load signals");
      } finally {
        setLoading(false);
      }
    }

    fetchSignals();
  }, [limit, refreshKey]);

  const handleRefresh = () => {
    setRefreshKey((k) => k + 1);
  };

  const formatPct = (v) =>
    v === null || v === undefined ? "-" : `${(v * 100).toFixed(2)}%`;

  const formatNum = (v, digits = 2) =>
    v === null || v === undefined ? "-" : v.toFixed(digits);

  const filteredResults =
    data && data.results
      ? data.results.filter((row) => {
          const rsi = row.rsi ?? 0;
          const score = row.score ?? 0;
          const tags = row.tags || [];

          if (score < minScore) return false;
          if (rsi < rsiMin || rsi > rsiMax) return false;
          if (requireBullish && !tags.includes("Bullish Momentum")) return false;
          if (requireUptrend && !tags.includes("Strong Uptrend")) return false;

          return true;
        })
      : [];

  const openChart = async (ticker) => {
    setSelectedTicker(ticker);
    setHistory(null);
    setHistoryError("");
    setHistoryLoading(true);
    try {
      const res = await fetch(`${API_BASE}/history/${ticker}?days=120`);
      if (!res.ok) {
        throw new Error(`Failed to load history (${res.status})`);
      }
      const json = await res.json();
      setHistory(json);
    } catch (e) {
      console.error(e);
      setHistoryError(e.message || "Error loading history");
    } finally {
      setHistoryLoading(false);
    }
  };

  const closeChart = () => {
    setSelectedTicker(null);
    setHistory(null);
    setHistoryError("");
  };

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <header className="mb-6">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight">
                SignalRadar
              </h1>
              <p className="text-slate-400 mt-1">
                Momentum &amp; volatility screener powered by your FastAPI backend.
              </p>
              {data && (
                <p className="text-xs text-slate-500 mt-1">
                  Universe: {data.tickers.join(", ")}
                </p>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-sm">
                <span className="text-slate-300">Top N:</span>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={limit}
                  onChange={(e) =>
                    setLimit(
                      Math.min(50, Math.max(1, Number(e.target.value) || 1))
                    )
                  }
                  className="w-20 rounded-md bg-slate-900 border border-slate-700 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </label>

              <button
                onClick={handleRefresh}
                className="inline-flex items-center rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-medium text-slate-950 hover:bg-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-60"
                disabled={loading}
              >
                {loading ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-4 text-sm">
            <label className="flex items-center gap-2">
              <span className="text-slate-300">Min score</span>
              <input
                type="number"
                value={minScore}
                onChange={(e) =>
                  setMinScore(Number(e.target.value) || 0)
                }
                className="w-20 rounded-md bg-slate-900 border border-slate-700 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </label>

            <label className="flex items-center gap-2">
              <span className="text-slate-300">RSI</span>
              <input
                type="number"
                value={rsiMin}
                onChange={(e) =>
                  setRsiMin(
                    Math.min(100, Math.max(0, Number(e.target.value) || 0))
                  )
                }
                className="w-16 rounded-md bg-slate-900 border border-slate-700 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
              <span className="text-slate-500">–</span>
              <input
                type="number"
                value={rsiMax}
                onChange={(e) =>
                  setRsiMax(
                    Math.min(100, Math.max(0, Number(e.target.value) || 100))
                  )
                }
                className="w-16 rounded-md bg-slate-900 border border-slate-700 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </label>

            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={requireBullish}
                onChange={(e) => setRequireBullish(e.target.checked)}
                className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-emerald-500 focus:ring-emerald-500"
              />
              <span className="text-slate-300">Bullish Momentum</span>
            </label>

            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={requireUptrend}
                onChange={(e) => setRequireUptrend(e.target.checked)}
                className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-emerald-500 focus:ring-emerald-500"
              />
              <span className="text-slate-300">Strong Uptrend</span>
            </label>

            <div className="mt-4 text-sm text-slate-300 w-full max-w-xl">
              <label className="block mb-1">
                Custom tickers (comma or space separated)
              </label>
              <textarea
                value={tickersText}
                onChange={(e) => setTickersText(e.target.value)}
                placeholder="Example: AAPL MSFT NVDA TSLA AMD ..."
                rows={2}
                className="w-full rounded-md bg-slate-900 border border-slate-700 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
              <p className="mt-1 text-xs text-slate-500">
                Leave blank to use the default large-cap universe.
              </p>
          </div>
          </div>
        </header>

        {error && (
          <div className="mb-4 rounded-md border border-red-500/60 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {error}
          </div>
        )}

        {!data && !loading && !error && (
          <p className="text-sm text-slate-400">
            No data yet. Click <span className="font-semibold">Refresh</span> to
            load signals.
          </p>
        )}

        {loading && (
          <p className="text-sm text-slate-400 mb-3">Loading signals…</p>
        )}

        {data && filteredResults.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40 shadow-lg shadow-emerald-500/5">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-slate-900/70 border-b border-slate-800">
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Rank
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-200">
                    Ticker
                  </th>
                  <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Score
                  </th>
                  <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Price
                  </th>
                  <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-400">
                    RSI
                  </th>
                  <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Vol xAvg
                  </th>
                  <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-400">
                    ATR%
                  </th>
                  <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-400">
                    5d %
                  </th>
                  <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-400">
                    20d %
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Tags
                  </th>
                  <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Chart
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredResults.map((row, idx) => (
                  <tr
                    key={row.ticker}
                    className="border-t border-slate-800/70 hover:bg-slate-900/70"
                  >
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {idx + 1}
                    </td>
                    <td className="px-3 py-2 font-semibold text-slate-100">
                      {row.ticker}
                    </td>
                    <td className="px-3 py-2 text-right font-semibold text-emerald-400">
                      {formatNum(row.score, 1)}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-200">
                      ${formatNum(row.close, 2)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {formatNum(row.rsi, 1)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {formatNum(row.vol_ratio, 2)}x
                    </td>
                    <td className="px-3 py-2 text-right">
                      {formatPct(row.atr_pct)}
                    </td>
                    <td
                      className={`px-3 py-2 text-right ${
                        row.ret_5d > 0
                          ? "text-emerald-400"
                          : row.ret_5d < 0
                          ? "text-rose-400"
                          : "text-slate-300"
                      }`}
                    >
                      {formatPct(row.ret_5d)}
                    </td>
                    <td
                      className={`px-3 py-2 text-right ${
                        row.ret_20d > 0
                          ? "text-emerald-400"
                          : row.ret_20d < 0
                          ? "text-rose-400"
                          : "text-slate-300"
                      }`}
                    >
                      {formatPct(row.ret_20d)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {(row.tags || []).map((tag) => (
                          <span
                            key={tag}
                            className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-300 border border-emerald-500/30"
                          >
                            {tag}
                          </span>
                        ))}
                        {(!row.tags || row.tags.length === 0) && (
                          <span className="text-xs text-slate-500">-</span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        onClick={() => openChart(row.ticker)}
                        className="text-xs rounded-md border border-emerald-500/40 px-2 py-1 text-emerald-300 hover:bg-emerald-500/10"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data && filteredResults.length === 0 && !loading && !error && (
          <p className="text-sm text-slate-400 mt-4">
            No rows match your current filters.
          </p>
        )}

        <p className="mt-6 text-xs text-slate-500">
          Scores are a composite of trend, RSI, recent returns, volume, and
          volatility computed in your Python/FastAPI backend.
        </p>
      </div>

      {selectedTicker && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-xl rounded-xl bg-slate-950 border border-slate-800 p-4 shadow-lg shadow-emerald-500/20">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold">
                {selectedTicker} – Price History
              </h2>
              <button
                onClick={closeChart}
                className="text-slate-400 hover:text-slate-100 text-sm"
              >
                Close
              </button>
            </div>

            {historyLoading && (
              <p className="text-sm text-slate-400">Loading chart…</p>
            )}

            {historyError && (
              <p className="text-sm text-red-400">{historyError}</p>
            )}

            {history && history.points && history.points.length > 0 && (
              <div className="mt-2">
                <Line
                  data={{
                    labels: history.points.map((p) => p.date),
                    datasets: [
                      {
                        label: "Close",
                        data: history.points.map((p) => p.close),
                        borderWidth: 2,
                        borderColor: "rgba(16, 185, 129, 1)",       // bright emerald line
                        backgroundColor: "rgba(16, 185, 129, 0.15)", // subtle fill under line
                        tension: 0.3,
                        pointRadius: 0,
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    plugins: {
                      legend: { display: false },
                    },
                    scales: {
                      x: {
                        ticks: { maxTicksLimit: 6, color: "#9ca3af" },
                        grid: { display: false },
                      },
                      y: {
                        ticks: { color: "#9ca3af" },
                        grid: { color: "rgba(148,163,184,0.2)" },
                      },
                    },
                  }}
                />
              </div>
            )}

            {history &&
              history.points &&
              history.points.length === 0 &&
              !historyLoading &&
              !historyError && (
                <p className="text-sm text-slate-400">
                  No history data available for this ticker.
                </p>
              )}
          </div>
        </div>
      )}
    </main>
  );
}