"""Unified CLI for the Home & Lifestyle Intelligence Pipeline and FastMCP Server."""

import argparse
import json
import logging
import sys
from app.db import (
    get_db_stats,
    get_market_metrics,
    get_product_evaluations,
    init_db,
    search_documents,
)
from app.ingest.feed_crawler import crawl_all_feeds, crawl_feed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("home-intel-cli")


def main():
    parser = argparse.ArgumentParser(
        prog="home-intel-mcp",
        description="Home, Real Estate, Renovation & Smart Living Intelligence Pipeline and FastMCP Server",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # init-db
    subparsers.add_parser("init-db", help="Initialize SQLite database schema and FTS5 indexes")

    # crawl-feeds
    p_crawl = subparsers.add_parser("crawl-feeds", help="Crawl configured RSS feeds")
    p_crawl.add_argument("--category", help="Filter by category (e.g. 'Smart Tech', 'Energy', 'Housing')")
    p_crawl.add_argument("--max", type=int, default=10, help="Max items per feed")

    # run-all
    subparsers.add_parser("run-all", help="Run full ingestion across all 17 feeds")

    # test-feed
    p_test = subparsers.add_parser("test-feed", help="Test ingestion on a single RSS feed URL")
    p_test.add_argument("url", help="RSS feed URL to test")
    p_test.add_argument("--name", default="Custom Feed", help="Source name")
    p_test.add_argument("--category", default="Smart Tech & IoT", help="Category name")

    # search
    p_search = subparsers.add_parser("search", help="Perform BM25 full-text search on local database")
    p_search.add_argument("query", help="Search query (e.g. 'Matter 1.3', 'mortgage rate', 'Powerwall')")
    p_search.add_argument("--category", help="Filter by category")
    p_search.add_argument("--limit", type=int, default=5, help="Number of results")

    # market-trends
    p_market = subparsers.add_parser("market-trends", help="Query macro housing and mortgage rate metrics")
    p_market.add_argument("--topic", help="Metric filter (e.g. 'Mortgage', 'Inventory')")
    p_market.add_argument("--limit", type=int, default=10, help="Limit results")

    # gear-picks
    p_gear = subparsers.add_parser("gear-picks", help="Query tested product evaluations and recommendations")
    p_gear.add_argument("--category", help="Product category")
    p_gear.add_argument("--product", help="Product or brand name")
    p_gear.add_argument("--limit", type=int, default=10, help="Limit results")

    # stats
    subparsers.add_parser("stats", help="Show database counts and category statistics")

    # serve-mcp
    p_mcp = subparsers.add_parser("serve-mcp", help="Start the FastMCP server")
    p_mcp.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="MCP transport mode")
    p_mcp.add_argument("--host", default="0.0.0.0", help="Host for SSE transport")
    p_mcp.add_argument("--port", type=int, default=8081, help="Port for SSE transport")

    # run-scheduler
    subparsers.add_parser("run-scheduler", help="Start background polling scheduler daemon")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "init-db":
        init_db()
        print("✅ Database initialized successfully.")

    elif args.command == "crawl-feeds":
        init_db()
        stats = crawl_all_feeds(category_filter=args.category, max_items_per_feed=args.max)
        print(f"✅ Ingested feeds: {json.dumps(stats, indent=2)}")

    elif args.command == "run-all":
        init_db()
        stats = crawl_all_feeds(max_items_per_feed=10)
        print(f"✅ Full ingestion complete:\n{json.dumps(stats, indent=2)}")

    elif args.command == "test-feed":
        init_db()
        src = {"name": args.name, "url": args.url, "category": args.category}
        ids = crawl_feed(src, max_items=3)
        print(f"✅ Processed {len(ids)} items from {args.url}")

    elif args.command == "search":
        results = search_documents(query=args.query, category=args.category, limit=args.limit)
        print(f"🔍 Found {len(results)} items for '{args.query}':\n")
        for r in results:
            print(f"- [{r['source_name']}] {r['title']}")
            print(f"  Category: {r['category']} | Link: {r['url']}")
            print(f"  Summary: {r['summary'][:200]}...\n")

    elif args.command == "market-trends":
        results = get_market_metrics(metric_name=args.topic, limit=args.limit)
        print(f"📈 Found {len(results)} market metrics:\n")
        for m in results:
            print(f"- {m['metric_name']}: {m['value']} ({m.get('period') or 'Current'})")
            print(f"  Source: {m['source_name']} | Title: {m['title']}")
            if m.get("context"):
                print(f"  Context: {m['context']}\n")

    elif args.command == "gear-picks":
        results = get_product_evaluations(category=args.category, product_name=args.product, limit=args.limit)
        print(f"🛠️ Found {len(results)} product evaluations:\n")
        for ev in results:
            print(f"- {ev['product_name']} ({ev.get('price_point') or 'N/A'}) — {ev['verdict']}")
            print(f"  Category: {ev['category']} | Tested by: {ev['source_name']}")
            print(f"  Pros: {', '.join(ev.get('pros', []))}")
            print(f"  Cons: {', '.join(ev.get('cons', []))}\n")

    elif args.command == "stats":
        stats = get_db_stats()
        print("📊 Home & Lifestyle Intelligence Database Stats:")
        print(json.dumps(stats, indent=2))

    elif args.command == "serve-mcp":
        from app.mcp_server import mcp
        if args.transport == "sse":
            mcp.run(transport="sse", host=args.host, port=args.port)
        else:
            mcp.run(transport="stdio")

    elif args.command == "run-scheduler":
        from app.scheduler import start_scheduler
        start_scheduler()


if __name__ == "__main__":
    main()
