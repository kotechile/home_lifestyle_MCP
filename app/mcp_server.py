"""FastMCP Server exposing Home, Real Estate, Renovation & Smart Living Intelligence to LLM clients."""

import json
import logging
from typing import Optional
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_config
from app.db import (
    get_db_stats,
    get_market_metrics,
    get_product_evaluations,
    get_recent_documents,
    init_db,
    search_documents,
)
from app.ingest.feed_crawler import crawl_all_feeds

logger = logging.getLogger(__name__)

# Ensure DB is initialized
init_db()

config = get_config()
mcp_cfg = config.get("mcp", {})

mcp = FastMCP(
    name=mcp_cfg.get("name", "home-lifestyle-intel"),
)


@mcp.tool()
def search_home_intelligence(query: str, category: Optional[str] = None, limit: int = 5) -> str:
    """Search across Smart Home, Residential Energy, Real Estate Economics, Architecture, and Zoning intelligence.

    Args:
        query: Keywords, technology, or topic (e.g. 'Matter 1.3', 'Powerwall 3', 'mortgage rates', 'ADU blueprint', 'heat pump rebate')
        category: Optional category filter: 'Smart Tech & IoT', 'Residential Energy', 'Housing Macro', 'Architecture', or 'Urban Policy'
        limit: Max results to return (default: 5)
    """
    results = search_documents(query=query, category=category, limit=limit)
    if not results:
        return f"No intelligence found matching query: '{query}'."

    output = [f"### 🔍 Found {len(results)} Home Intelligence Items for '{query}':\n"]
    for r in results:
        output.append(f"#### [{r['source_name']}] {r['title']}")
        output.append(f"- **Category:** {r['category']} | **Published:** {r.get('published_at', 'N/A')}")
        output.append(f"- **URL:** {r['url']}")
        if r.get("topics"):
            output.append(f"- **Topics:** {', '.join(r['topics'])}")
        output.append(f"- **Brief:**\n{r.get('summary', 'No summary available.')}\n")

        takeaways = r.get("takeaways", [])
        if takeaways:
            output.append("- **Key Actionable Takeaways / DIY Considerations:**")
            for t in takeaways[:3]:
                output.append(f"  * {t}")
            output.append("")

        metrics = r.get("key_metrics", [])
        if metrics:
            output.append("- **Highlighted Metrics:**")
            for m in metrics[:3]:
                output.append(f"  * `{m.get('metric')}`: {m.get('context')}")
            output.append("")
        output.append("---\n")

    return "\n".join(output)


@mcp.tool()
def get_latest_home_insights(category: Optional[str] = None, days_back: int = 14, limit: int = 5) -> str:
    """Retrieve the most recent home, real estate, energy, and architecture articles.

    Args:
        category: Optional filter: 'Smart Tech & IoT', 'Residential Energy', 'Housing Macro', 'Architecture', or 'Urban Policy'
        days_back: How many days back to look (default: 14)
        limit: Maximum results (default: 5)
    """
    results = get_recent_documents(category=category, days_back=days_back, limit=limit)
    if not results:
        return f"No recent insights found within the last {days_back} days."

    output = [f"### 🏡 Latest {len(results)} Home & Lifestyle Insights (Past {days_back} Days):\n"]
    for r in results:
        output.append(f"#### [{r['source_name']}] {r['title']}")
        output.append(f"- **Category:** {r['category']} | **Date:** {r.get('published_at', 'N/A')}")
        output.append(f"- **Link:** {r['url']}")
        output.append(f"- **Summary:** {r.get('summary', '')}\n")
    return "\n".join(output)


@mcp.tool()
def get_market_and_mortgage_trends(topic: Optional[str] = None, limit: int = 10) -> str:
    """Query macro housing valuation shifts, daily mortgage rates, housing starts, and inventory metrics from Calculated Risk, Redfin, Mortgage News Daily, and Wolf Street.

    Args:
        topic: Keyword or metric name (e.g. 'Mortgage Rate', 'Inventory', 'Home Prices', 'Housing Starts')
        limit: Maximum results (default: 10)
    """
    metrics = get_market_metrics(metric_name=topic, limit=limit)
    if not metrics:
        return "No housing market or mortgage metrics found matching query."

    output = [f"### 📈 Macro Housing & Mortgage Rate Indicators ({len(metrics)} data points):\n"]
    for m in metrics:
        output.append(f"- **{m['metric_name']}:** `{m['value']}` ({m.get('period') or 'Current'})")
        output.append(f"  * **Source:** [{m['source_name']}]({m['url']}) - *{m['title']}*")
        if m.get("context"):
            output.append(f"  * **Context:** {m['context']}")
        output.append("")
    return "\n".join(output)


@mcp.tool()
def get_product_recommendations(category: Optional[str] = None, product_name: Optional[str] = None, limit: int = 10) -> str:
    """Query tested product reviews, appliances, smart home hardware, and tools from Wirecutter, The Verge, Ars Technica, and Home Assistant.

    Args:
        category: Filter by product category (e.g. 'Smart Lock', 'Heat Pump', 'Wi-Fi 7', 'Induction', 'Solar Battery')
        product_name: Filter by product or brand name (e.g. 'Ecobee', 'Tesla Powerwall', 'Matter', 'Aqara')
        limit: Maximum results (default: 10)
    """
    evals = get_product_evaluations(category=category, product_name=product_name, limit=limit)
    if not evals:
        return "No product recommendations or evaluations found matching criteria."

    output = [f"### 🛠️ Tested Gear & Appliance Recommendations ({len(evals)} items):\n"]
    for ev in evals:
        price = f" ({ev['price_point']})" if ev.get("price_point") else ""
        output.append(f"#### {ev['product_name']}{price} — **{ev['verdict']}**")
        output.append(f"- **Category:** {ev['category']} | **Tested by:** {ev['source_name']}")
        output.append(f"- **Source Article:** [{ev['title']}]({ev['url']})")

        pros = ev.get("pros", [])
        if pros:
            output.append("- **Pros:** " + ", ".join(pros))

        cons = ev.get("cons", [])
        if cons:
            output.append("- **Cons:** " + ", ".join(cons))
        output.append("")

    return "\n".join(output)


@mcp.tool()
def get_diy_and_renovation_ideas(topic: Optional[str] = None, limit: int = 5) -> str:
    """Retrieve modern residential blueprints, ADU ideas, interior layouts, structural renovations, and zoning rules from Dwell, Remodelista, Dezeen, and Planetizen.

    Args:
        topic: Specific project type or keyword (e.g. 'ADU', 'kitchen remodel', 'zoning reform', 'lighting', 'insulation')
        limit: Maximum results (default: 5)
    """
    if topic:
        results = search_documents(query=topic, category="Architecture", limit=limit)
        if not results:
            results = search_documents(query=topic, limit=limit)
    else:
        results = get_recent_documents(category="Architecture", days_back=30, limit=limit)

    if not results:
        return "No DIY or renovation ideas found matching topic."

    output = [f"### 📐 Architecture, Renovation & DIY Blueprint Insights ({len(results)} items):\n"]
    for r in results:
        output.append(f"#### [{r['source_name']}] {r['title']}")
        output.append(f"- **Link:** {r['url']}")
        output.append(f"- **Concept Summary:** {r.get('summary')}")
        takeaways = r.get("takeaways", [])
        if takeaways:
            output.append("- **Design / Implementation Takeaways:**")
            for t in takeaways:
                output.append(f"  * {t}")
        output.append("")

    return "\n".join(output)


@mcp.tool()
def trigger_pipeline_refresh(category: Optional[str] = "all") -> str:
    """Trigger an on-demand background refresh of RSS feeds.

    Args:
        category: 'all', 'smart_home', 'energy', 'real_estate', 'architecture', or 'policy'
    """
    category_filter = None if category == "all" else category
    stats = crawl_all_feeds(category_filter=category_filter)
    return f"Pipeline refresh complete. Feed update stats:\n```json\n{json.dumps(stats, indent=2)}\n```"


@mcp.tool()
def get_pipeline_stats() -> str:
    """Return database counts, category distribution, and indexing health."""
    stats = get_db_stats()
    return f"Home & Lifestyle Database Health & Statistics:\n```json\n{json.dumps(stats, indent=2)}\n```"


# --- Starlette HTTP Endpoints for n8n Webhooks & Health Monitoring ---

@mcp.custom_route("/health", methods=["GET"])
async def http_health(request: Request) -> JSONResponse:
    """Health check endpoint for Coolify / Docker."""
    return JSONResponse({"status": "healthy", "service": "home-lifestyle-intel-mcp"})


@mcp.custom_route("/api/stats", methods=["GET"])
async def http_stats(request: Request) -> JSONResponse:
    """Return database statistics as JSON."""
    return JSONResponse(get_db_stats())


@mcp.custom_route("/api/insights/recent", methods=["GET"])
async def http_recent_insights(request: Request) -> JSONResponse:
    """Return recent articles as JSON for automated briefings."""
    category = request.query_params.get("category")
    days_back = int(request.query_params.get("days_back", 7))
    limit = int(request.query_params.get("limit", 10))
    results = get_recent_documents(category=category, days_back=days_back, limit=limit)
    return JSONResponse({"count": len(results), "items": results})


@mcp.custom_route("/api/crawl", methods=["POST"])
async def http_crawl(request: Request) -> JSONResponse:
    """Trigger feed crawl via HTTP webhook."""
    category = request.query_params.get("category")
    max_items = int(request.query_params.get("max", 5))
    stats = crawl_all_feeds(category_filter=category, max_items_per_feed=max_items)
    return JSONResponse({"status": "completed", "stats": stats})


# ASGI app for Uvicorn deployment in Coolify / Docker
app = mcp.http_app()


if __name__ == "__main__":
    mcp.run()
