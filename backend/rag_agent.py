import os
import numpy as np
from typing import Optional

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

_embedding_model = None
_agent = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from fastembed import TextEmbedding
        _embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _embedding_model


def embed(text: str) -> list:
    model = get_embedding_model()
    return list(model.embed([text]))[0].tolist()


def build_embedding_text(r: dict) -> str:
    tags_str = ", ".join(r.get("tags") or []) or "none"
    rsi = r.get("rsi")
    rsi_str = f"{rsi:.1f}" if rsi is not None else "n/a"
    ret_5d = r.get("ret_5d") or 0.0
    ret_20d = r.get("ret_20d") or 0.0
    vol = r.get("vol_ratio")
    vol_str = f"{vol:.2f}x" if vol is not None else "n/a"
    atr = r.get("atr_pct")
    atr_str = f"{atr*100:.2f}%" if atr is not None else "n/a"
    return (
        f"{r['ticker']} signal: score={r['score']}, RSI={rsi_str}, "
        f"tags=[{tags_str}], 5d_return={ret_5d*100:.1f}%, "
        f"20d_return={ret_20d*100:.1f}%, vol={vol_str}, ATR={atr_str}, "
        f"notes={r.get('notes', '')}"
    )


def embed_and_store_snapshots(results: list, snapshot_ids: list) -> None:
    """Generate and persist embeddings for a batch of screener results."""
    from database import update_snapshot_embedding
    for result, (sid, _ticker) in zip(results, snapshot_ids):
        try:
            text = build_embedding_text(result)
            embedding = embed(text)
            update_snapshot_embedding(sid, text, embedding)
        except Exception as e:
            print(f"[RAG] embed failed for {result.get('ticker')}: {e}")


def get_agent():
    global _agent
    if _agent is not None:
        return _agent
    if not GROQ_API_KEY:
        return None

    from langchain_groq import ChatGroq
    from langchain_core.tools import tool
    from langgraph.prebuilt import create_react_agent
    from database import semantic_search

    @tool
    def search_signals(query: str) -> str:
        """Search recent stock signal snapshots using semantic similarity.
        Returns top matching tickers with scores, RSI, momentum tags, and return data.
        Always call this before answering questions about specific stocks or market signals."""
        query_vec = np.array(embed(query), dtype=np.float32)
        results = semantic_search(query_vec, top_k=5)
        if not results:
            return (
                "No signal snapshots found. The /signals endpoint has not been called yet, "
                "or no embeddings have been generated."
            )
        lines = []
        for r in results:
            captured = (
                r["captured_at"].strftime("%Y-%m-%d %H:%M")
                if r.get("captured_at") else "unknown"
            )
            sim = r.get("similarity", 0.0)
            lines.append(
                f"- {r['ticker']} (captured {captured}, similarity={sim:.3f}): "
                f"{r.get('embedding_text', 'no details')}"
            )
        return "\n".join(lines)

    llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)
    _agent = create_react_agent(
        llm,
        tools=[search_signals],
        messages_modifier=(
            "You are SignalRadar's AI analyst. "
            "Always call search_signals to retrieve relevant stock data before answering. "
            "Ground every claim in retrieved metrics (score, RSI, tags, returns). "
            "Be concise — 3-5 sentences per ticker, bullet points for multiple tickers. "
            "If no data is found, say so and suggest running the screener first."
        ),
    )
    return _agent


async def run_agent(question: str) -> str:
    if not GROQ_API_KEY:
        return (
            "GROQ_API_KEY is not configured. "
            "Add it to your environment variables to enable AI analysis."
        )
    agent = get_agent()
    if agent is None:
        return "Agent failed to initialize. Check GROQ_API_KEY."
    result = await agent.ainvoke({"messages": [{"role": "user", "content": question}]})
    return result["messages"][-1].content
