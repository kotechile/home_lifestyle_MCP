"""RSS / Atom feed crawler for Home & Lifestyle sources."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import feedparser
import httpx
import trafilatura

from app.config import get_config
from app.db import (
    document_exists,
    insert_document,
    insert_market_metric,
    insert_product_evaluation,
)
from app.llm import analyze_article

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_article_content(url: str, timeout: float = 15.0) -> Optional[str]:
    """Extract clean article markdown using Trafilatura, with Jina Reader fallback."""
    try:
        with httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                extracted = trafilatura.extract(
                    resp.text,
                    url=url,
                    include_links=True,
                    include_tables=True,
                    output_format="markdown",
                )
                if extracted and len(extracted.strip()) > 250:
                    return extracted

            # Fallback for dynamic / SPA sites: Jina Reader API
            jina_url = f"https://r.jina.ai/{url}"
            jina_resp = client.get(jina_url, timeout=20.0)
            if jina_resp.status_code == 200 and len(jina_resp.text.strip()) > 200:
                return jina_resp.text
    except Exception as e:
        logger.warning(f"Failed to fetch/extract content from {url}: {e}")

    return None


def crawl_feed(source: Dict[str, Any], max_items: int = 10, db_path: Optional[str] = None) -> List[str]:
    """Crawl a single RSS feed and ingest unseen articles."""
    source_name = source["name"]
    feed_url = source["url"]
    category = source.get("category", "General")
    default_tags = source.get("tags", [])

    logger.info(f"Checking feed: {source_name} ({feed_url})")
    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        logger.error(f"Failed to parse RSS feed {feed_url}: {e}")
        return []

    ingested_ids = []

    for entry in feed.entries[:max_items]:
        link = entry.get("link")
        if not link or document_exists(link, db_path=db_path):
            continue

        title = entry.get("title", "Untitled")
        published_at = entry.get("published", entry.get("updated", datetime.now(timezone.utc).isoformat()))

        logger.info(f"New article discovered: {title} ({link})")

        # Fetch full article text
        content = fetch_article_content(link)
        if not content:
            # Fallback to feed summary or content:encoded if page fetch fails
            if "content" in entry and entry.content:
                content = entry.content[0].value
            else:
                content = entry.get("summary", "")

        if not content or len(content.strip()) < 40:
            logger.warning(f"Skipping article due to insufficient content: {link}")
            continue

        # Extract structured takeaways, metrics, and tags
        analysis = analyze_article(
            title=title,
            content=content,
            source_name=source_name,
            category=category,
        )

        all_topics = list(dict.fromkeys(default_tags + analysis.get("topics", [])))

        # Insert document into SQLite
        doc_id = insert_document(
            source_name=source_name,
            category=category,
            url=link,
            title=title,
            raw_content=content,
            summary=analysis.get("summary", ""),
            key_metrics=analysis.get("key_metrics", []),
            topics=all_topics,
            takeaways=analysis.get("takeaways", []),
            published_at=published_at,
            db_path=db_path,
        )
        ingested_ids.append(doc_id)

        # Ingest structured market metrics if detected
        for mm in analysis.get("market_metrics", []):
            metric_name = mm.get("metric_name")
            value = mm.get("value")
            if metric_name and value:
                insert_market_metric(
                    document_id=doc_id,
                    metric_name=metric_name,
                    value=value,
                    period=mm.get("period"),
                    source_name=source_name,
                    context=mm.get("context", title),
                    db_path=db_path,
                )

        # Ingest structured product evaluations if detected
        for pe in analysis.get("product_evaluations", []):
            product_name = pe.get("product_name")
            if product_name:
                insert_product_evaluation(
                    document_id=doc_id,
                    product_name=product_name,
                    category=pe.get("category", category),
                    verdict=pe.get("verdict", "Evaluated"),
                    pros=pe.get("pros", []),
                    cons=pe.get("cons", []),
                    price_point=pe.get("price_point"),
                    db_path=db_path,
                )

    logger.info(f"Feed '{source_name}' processed: {len(ingested_ids)} new articles ingested.")
    return ingested_ids


def crawl_all_feeds(
    category_filter: Optional[str] = None,
    max_items_per_feed: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Crawl all configured feeds with optional category filtering."""
    config = get_config()
    ingest_cfg = config.get("ingest", {})
    feeds = ingest_cfg.get("feeds", [])
    default_max = ingest_cfg.get("max_items_per_feed", 10)
    max_items = max_items_per_feed or default_max

    stats: Dict[str, int] = {}
    total_ingested = 0

    for source in feeds:
        category = source.get("category", "")
        if category_filter and category_filter.lower() not in category.lower():
            continue

        feed_name = source.get("name", source.get("url"))
        try:
            ids = crawl_feed(source, max_items=max_items, db_path=db_path)
            stats[feed_name] = len(ids)
            total_ingested += len(ids)
        except Exception as e:
            logger.error(f"Error crawling feed '{feed_name}': {e}")
            stats[feed_name] = 0

    return {
        "total_feeds_checked": len(stats),
        "total_articles_ingested": total_ingested,
        "by_feed": stats,
    }
