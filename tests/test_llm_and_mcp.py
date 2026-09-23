"""Unit tests for heuristic extractor and FastMCP tool definitions."""

import os
import tempfile
import pytest

from app.db import (
    init_db,
    insert_document,
    insert_market_metric,
    insert_product_evaluation,
)
from app.llm import (
    _fallback_extract,
    get_llm_client,
    get_model_name,
    resolve_provider,
)

try:
    from app.mcp_server import (
        get_diy_and_renovation_ideas,
        get_latest_home_insights,
        get_market_and_mortgage_trends,
        get_pipeline_stats,
        get_product_recommendations,
        search_home_intelligence,
    )
    HAS_MCP = True
except ImportError:
    HAS_MCP = False



@pytest.fixture
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    monkeypatch.setenv("DB_PATH", path)
    from app import config
    config._CONFIG = None
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_heuristic_extraction():
    title = "Tesla Powerwall 3 Inverter Capabilities and California Solar Rebates"
    content = (
        "The new Tesla Powerwall 3 includes an integrated solar inverter supporting up to 20 kW of solar panels. "
        "Homeowners can receive up to a $7,500 tax credit or state clean energy rebate. "
        "Typical home batteries deliver 13.5 kWh of usable storage capacity. "
        "Mortgage rates also affect green renovation loans, with current 30-year fixed rates around 6.75%."
    )
    result = _fallback_extract(title, content, category="Residential Energy & Clean Tech")

    assert len(result["summary"]) > 20
    assert len(result["key_metrics"]) >= 1
    # Check that tags were extracted
    topics = result["topics"]
    assert any("Solar" in t or "Battery" in t or "Powerwall" in t for t in topics)
    # Check takeaways
    assert len(result["takeaways"]) >= 1


def test_deepseek_configuration(monkeypatch):
    # Test provider and model resolution with user env vars
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")

    assert resolve_provider() == "deepseek"
    assert get_model_name() == "deepseek-flash"

    client = get_llm_client()
    assert client is not None
    assert str(client.base_url).rstrip("/") == "https://api.deepseek.com"
    assert client.api_key == "sk-deepseek-test"


def test_deepseek_fallback_key(monkeypatch):
    # Test fallback to LLM_API_KEY if DEEPSEEK_API_KEY is not explicitly set
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-generic-llm-key")

    assert resolve_provider() == "deepseek"
    client = get_llm_client()
    assert client is not None
    assert client.api_key == "sk-generic-llm-key"


@pytest.mark.skipif(not HAS_MCP, reason="fastmcp is not installed in local environment")
def test_mcp_tools(temp_db):
    # Seed document
    doc_id = insert_document(
        source_name="Dwell",
        category="Architecture, DIY & Design",
        url="https://www.dwell.com/article/modern-adu-san-francisco-renovation",
        title="Prefab ADU That Doubled Living Space in Urban Lot",
        raw_content="A clever 650 sq ft accessory dwelling unit built behind a 1920s bungalow with zoning permits.",
        summary="Case study of an ADU providing multi-generational living space.",
        takeaways=["Check local ADU setbacks and maximum height restrictions before blueprint finalization."],
        topics=["ADU", "Architecture", "Renovation"],
        db_path=temp_db,
    )

    insert_market_metric(
        document_id=doc_id,
        metric_name="ADU Construction Cost",
        value="$350/sq ft",
        source_name="Dwell",
        context="Northern California urban build",
        db_path=temp_db,
    )

    insert_product_evaluation(
        document_id=doc_id,
        product_name="Fleetwood Sliders",
        category="Architectural Glazing",
        verdict="Recommended",
        pros=["Ultra-thin sightlines"],
        cons=["Premium price"],
        db_path=temp_db,
    )

    # Test search_home_intelligence
    res_search = search_home_intelligence("ADU")
    assert "Prefab ADU" in res_search

    # Test get_latest_home_insights
    res_insights = get_latest_home_insights(days_back=30)
    assert "Prefab ADU" in res_insights

    # Test get_market_and_mortgage_trends
    res_market = get_market_and_mortgage_trends(topic="ADU")
    assert "$350/sq ft" in res_market

    # Test get_product_recommendations
    res_gear = get_product_recommendations(product_name="Fleetwood")
    assert "Fleetwood Sliders" in res_gear

    # Test get_diy_and_renovation_ideas
    res_diy = get_diy_and_renovation_ideas(topic="ADU")
    assert "Prefab ADU" in res_diy

    # Test get_pipeline_stats
    res_stats = get_pipeline_stats()
    assert "total_documents" in res_stats
