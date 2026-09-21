"""Database storage and full-text search layer using SQLite and FTS5 for Home Intelligence."""

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import get_config


def get_db_path() -> str:
    config = get_config()
    return config.get("storage", {}).get("db_path", "data/home_intelligence.db")


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def generate_doc_id(url: str) -> str:
    """Generate deterministic SHA256 ID from URL."""
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:24]


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database tables and FTS5 full-text search indexes."""
    conn = get_connection(db_path)
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,       -- e.g. 'Home Assistant Blog', 'Wirecutter'
            category TEXT NOT NULL,          -- e.g. 'Smart Tech & IoT', 'Housing Macro & Real Estate'
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            published_at TEXT,
            raw_content TEXT,                -- Full article markdown or extracted text
            summary TEXT,                    -- Executive brief / overview
            key_metrics TEXT,                -- JSON string of metrics/data points
            topics TEXT,                     -- JSON array of tags
            takeaways TEXT,                  -- JSON array of actionable takeaways/DIY tips
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_docs_category ON documents(category);
        CREATE INDEX IF NOT EXISTS idx_docs_source_name ON documents(source_name);
        CREATE INDEX IF NOT EXISTS idx_docs_published_at ON documents(published_at);
        CREATE INDEX IF NOT EXISTS idx_docs_url ON documents(url);

        CREATE TABLE IF NOT EXISTS market_metrics (
            id TEXT PRIMARY KEY,
            document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
            metric_name TEXT NOT NULL,       -- e.g. '30-Year Mortgage Rate', 'Active Inventory'
            value TEXT NOT NULL,             -- e.g. '6.85%', '+12.4% YoY'
            period TEXT,                     -- e.g. 'September 2026', 'Weekly'
            source_name TEXT NOT NULL,
            context TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_metrics_name ON market_metrics(metric_name);
        CREATE INDEX IF NOT EXISTS idx_metrics_source ON market_metrics(source_name);

        CREATE TABLE IF NOT EXISTS product_evaluations (
            id TEXT PRIMARY KEY,
            document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,          -- e.g. 'Heat Pump', 'Smart Lock', 'Wi-Fi 7 Router'
            verdict TEXT NOT NULL,           -- e.g. 'Top Pick', 'Best Budget', 'Recommended'
            pros TEXT,                       -- JSON array
            cons TEXT,                       -- JSON array
            price_point TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_eval_product ON product_evaluations(product_name);
        CREATE INDEX IF NOT EXISTS idx_eval_category ON product_evaluations(category);

        -- Virtual FTS5 table for full-text search
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
            id UNINDEXED,
            title,
            summary,
            raw_content,
            source_name,
            category,
            topics,
            tokenize = 'porter unicode61'
        );

        -- Triggers to keep FTS index synchronized with documents table
        CREATE TRIGGER IF NOT EXISTS trg_docs_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts (id, title, summary, raw_content, source_name, category, topics)
            VALUES (new.id, new.title, new.summary, new.raw_content, new.source_name, new.category, new.topics);
        END;

        CREATE TRIGGER IF NOT EXISTS trg_docs_ad AFTER DELETE ON documents BEGIN
            DELETE FROM documents_fts WHERE id = old.id;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_docs_au AFTER UPDATE ON documents BEGIN
            DELETE FROM documents_fts WHERE id = old.id;
            INSERT INTO documents_fts (id, title, summary, raw_content, source_name, category, topics)
            VALUES (new.id, new.title, new.summary, new.raw_content, new.source_name, new.category, new.topics);
        END;
        """)
    conn.close()


def document_exists(url: str, db_path: Optional[str] = None) -> bool:
    """Check if a document URL has already been processed."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM documents WHERE url = ?", (url,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def insert_document(
    source_name: str,
    category: str,
    url: str,
    title: str,
    raw_content: str,
    summary: str = "",
    key_metrics: Optional[List[Dict[str, Any]]] = None,
    topics: Optional[List[str]] = None,
    takeaways: Optional[List[str]] = None,
    published_at: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    """Insert or update a document in the database."""
    doc_id = generate_doc_id(url)
    metrics_json = json.dumps(key_metrics or [], ensure_ascii=False)
    topics_json = json.dumps(topics or [], ensure_ascii=False)
    takeaways_json = json.dumps(takeaways or [], ensure_ascii=False)

    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO documents (
                id, source_name, category, url, title, published_at,
                raw_content, summary, key_metrics, topics, takeaways
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                source_name = excluded.source_name,
                category = excluded.category,
                title = excluded.title,
                raw_content = excluded.raw_content,
                summary = excluded.summary,
                key_metrics = excluded.key_metrics,
                topics = excluded.topics,
                takeaways = excluded.takeaways,
                published_at = COALESCE(excluded.published_at, documents.published_at)
            """,
            (
                doc_id,
                source_name,
                category,
                url,
                title,
                published_at,
                raw_content,
                summary,
                metrics_json,
                topics_json,
                takeaways_json,
            ),
        )
    conn.close()
    return doc_id


def insert_market_metric(
    document_id: str,
    metric_name: str,
    value: str,
    source_name: str,
    period: Optional[str] = None,
    context: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    metric_id = hashlib.sha256(f"{document_id}_{metric_name}_{value}".encode("utf-8")).hexdigest()[:24]
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO market_metrics (
                id, document_id, metric_name, value, period, source_name, context
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                value = excluded.value,
                period = excluded.period,
                context = excluded.context
            """,
            (metric_id, document_id, metric_name, value, period, source_name, context),
        )
    conn.close()
    return metric_id


def insert_product_evaluation(
    document_id: str,
    product_name: str,
    category: str,
    verdict: str,
    pros: Optional[List[str]] = None,
    cons: Optional[List[str]] = None,
    price_point: Optional[str] = None,
    db_path: Optional[str] = None,
) -> str:
    eval_id = hashlib.sha256(f"{document_id}_{product_name}".encode("utf-8")).hexdigest()[:24]
    pros_json = json.dumps(pros or [], ensure_ascii=False)
    cons_json = json.dumps(cons or [], ensure_ascii=False)

    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO product_evaluations (
                id, document_id, product_name, category, verdict, pros, cons, price_point
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                category = excluded.category,
                verdict = excluded.verdict,
                pros = excluded.pros,
                cons = excluded.cons,
                price_point = excluded.price_point
            """,
            (eval_id, document_id, product_name, category, verdict, pros_json, cons_json, price_point),
        )
    conn.close()
    return eval_id


def search_documents(
    query: str,
    category: Optional[str] = None,
    limit: int = 10,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Perform BM25 full-text search with optional category filtering."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    clean_query = query.replace('"', '""').strip()
    if not clean_query:
        return []

    if category:
        sql = """
            SELECT d.id, d.source_name, d.category, d.url, d.title, d.published_at,
                   d.summary, d.key_metrics, d.topics, d.takeaways, d.created_at,
                   bm25(documents_fts) AS rank
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.id
            WHERE documents_fts MATCH ? AND d.category LIKE ?
            ORDER BY rank
            LIMIT ?
        """
        cur.execute(sql, (clean_query, f"%{category}%", limit))
    else:
        sql = """
            SELECT d.id, d.source_name, d.category, d.url, d.title, d.published_at,
                   d.summary, d.key_metrics, d.topics, d.takeaways, d.created_at,
                   bm25(documents_fts) AS rank
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.id
            WHERE documents_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        cur.execute(sql, (clean_query, limit))

    results = []
    for row in cur.fetchall():
        item = dict(row)
        item["key_metrics"] = json.loads(item["key_metrics"]) if item.get("key_metrics") else []
        item["topics"] = json.loads(item["topics"]) if item.get("topics") else []
        item["takeaways"] = json.loads(item["takeaways"]) if item.get("takeaways") else []
        results.append(item)

    conn.close()
    return results


def get_recent_documents(
    category: Optional[str] = None,
    days_back: int = 7,
    limit: int = 10,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch the most recently ingested intelligence documents."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d %H:%M:%S")

    if category:
        sql = """
            SELECT id, source_name, category, url, title, published_at,
                   summary, key_metrics, topics, takeaways, created_at
            FROM documents
            WHERE category LIKE ? AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
        """
        cur.execute(sql, (f"%{category}%", cutoff_date, limit))
    else:
        sql = """
            SELECT id, source_name, category, url, title, published_at,
                   summary, key_metrics, topics, takeaways, created_at
            FROM documents
            WHERE created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
        """
        cur.execute(sql, (cutoff_date, limit))

    results = []
    for row in cur.fetchall():
        item = dict(row)
        item["key_metrics"] = json.loads(item["key_metrics"]) if item.get("key_metrics") else []
        item["topics"] = json.loads(item["topics"]) if item.get("topics") else []
        item["takeaways"] = json.loads(item["takeaways"]) if item.get("takeaways") else []
        results.append(item)

    conn.close()
    return results


def get_market_metrics(
    metric_name: Optional[str] = None,
    limit: int = 15,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query macro housing data, mortgage rates, and inventory metrics."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    if metric_name:
        sql = """
            SELECT m.id, m.metric_name, m.value, m.period, m.source_name, m.context,
                   d.title, d.url, m.created_at
            FROM market_metrics m
            JOIN documents d ON d.id = m.document_id
            WHERE m.metric_name LIKE ? OR m.context LIKE ?
            ORDER BY m.created_at DESC
            LIMIT ?
        """
        cur.execute(sql, (f"%{metric_name}%", f"%{metric_name}%", limit))
    else:
        sql = """
            SELECT m.id, m.metric_name, m.value, m.period, m.source_name, m.context,
                   d.title, d.url, m.created_at
            FROM market_metrics m
            JOIN documents d ON d.id = m.document_id
            ORDER BY m.created_at DESC
            LIMIT ?
        """
        cur.execute(sql, (limit,))

    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results


def get_product_evaluations(
    category: Optional[str] = None,
    product_name: Optional[str] = None,
    limit: int = 15,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query product reviews, ratings, and recommendations."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    conditions = []
    params: List[Any] = []

    if category:
        conditions.append("p.category LIKE ?")
        params.append(f"%{category}%")
    if product_name:
        conditions.append("p.product_name LIKE ?")
        params.append(f"%{product_name}%")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT p.id, p.product_name, p.category, p.verdict, p.pros, p.cons,
               p.price_point, d.title, d.url, d.source_name, p.created_at
        FROM product_evaluations p
        JOIN documents d ON d.id = p.document_id
        {where_clause}
        ORDER BY p.created_at DESC
        LIMIT ?
    """
    params.append(limit)
    cur.execute(sql, tuple(params))

    results = []
    for row in cur.fetchall():
        item = dict(row)
        item["pros"] = json.loads(item["pros"]) if item.get("pros") else []
        item["cons"] = json.loads(item["cons"]) if item.get("cons") else []
        results.append(item)

    conn.close()
    return results


def get_db_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Return database statistics and counts grouped by category and source."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute("SELECT category, COUNT(*) as count FROM documents GROUP BY category")
    by_category = {row["category"]: row["count"] for row in cur.fetchall()}

    cur.execute("SELECT source_name, COUNT(*) as count FROM documents GROUP BY source_name")
    by_source = {row["source_name"]: row["count"] for row in cur.fetchall()}

    cur.execute("SELECT COUNT(*) as count FROM documents")
    total_docs = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) as count FROM market_metrics")
    total_metrics = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) as count FROM product_evaluations")
    total_evals = cur.fetchone()["count"]

    conn.close()
    return {
        "total_documents": total_docs,
        "by_category": by_category,
        "by_source": by_source,
        "market_metrics_count": total_metrics,
        "product_evaluations_count": total_evals,
    }
