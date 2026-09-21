"""Unit tests for SQLite database schema, FTS5 search, metrics, and product evaluations."""

import os
import tempfile
import pytest

from app.db import (
    document_exists,
    get_db_stats,
    get_market_metrics,
    get_product_evaluations,
    get_recent_documents,
    init_db,
    insert_document,
    insert_market_metric,
    insert_product_evaluation,
    search_documents,
)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_init_db(temp_db):
    assert os.path.exists(temp_db)
    stats = get_db_stats(temp_db)
    assert stats["total_documents"] == 0
    assert stats["market_metrics_count"] == 0
    assert stats["product_evaluations_count"] == 0


def test_insert_and_search_document(temp_db):
    doc_id = insert_document(
        source_name="Home Assistant Blog",
        category="Smart Tech & IoT",
        url="https://www.home-assistant.io/blog/2026/09/matter-1-4-release",
        title="Home Assistant 2026.9: Matter 1.4 and Energy Automation",
        raw_content="Home Assistant 2026.9 introduces native Matter 1.4 support, solar inverter controls, and local-first Thread routing.",
        summary="Major release adding Matter 1.4 protocol and enhanced solar battery controls.",
        key_metrics=[{"metric": "10x faster", "context": "Matter commissioning speed"}],
        topics=["Matter", "Thread", "Home Assistant", "Solar"],
        takeaways=["Ensure Thread border routers are updated to 2026 firmware."],
        published_at="2026-09-15T12:00:00Z",
        db_path=temp_db,
    )

    assert doc_id is not None
    assert document_exists("https://www.home-assistant.io/blog/2026/09/matter-1-4-release", db_path=temp_db)
    assert not document_exists("https://random-other-url.com", db_path=temp_db)

    # Search via FTS5 BM25
    results = search_documents("Matter", db_path=temp_db)
    assert len(results) == 1
    assert results[0]["title"] == "Home Assistant 2026.9: Matter 1.4 and Energy Automation"
    assert "Matter" in results[0]["topics"]
    assert results[0]["category"] == "Smart Tech & IoT"


def test_market_metrics(temp_db):
    doc_id = insert_document(
        source_name="Mortgage News Daily",
        category="Housing Macro & Real Estate",
        url="https://www.mortgagenewsdaily.com/news/09202026-rates",
        title="30-Year Fixed Mortgage Rates Hold Steady at 6.85%",
        raw_content="Mortgage rates showed little movement today ahead of the upcoming FOMC meeting.",
        summary="30-year fixed rate benchmark at 6.85%.",
        db_path=temp_db,
    )

    m_id = insert_market_metric(
        document_id=doc_id,
        metric_name="30-Year Fixed Mortgage Rate",
        value="6.85%",
        source_name="Mortgage News Daily",
        period="September 2026",
        context="Ahead of FOMC rate decision",
        db_path=temp_db,
    )
    assert m_id is not None

    metrics = get_market_metrics(metric_name="Mortgage", db_path=temp_db)
    assert len(metrics) == 1
    assert metrics[0]["value"] == "6.85%"
    assert metrics[0]["source_name"] == "Mortgage News Daily"


def test_product_evaluations(temp_db):
    doc_id = insert_document(
        source_name="Wirecutter (Home)",
        category="Architecture, DIY & Design",
        url="https://www.nytimes.com/wirecutter/reviews/best-heat-pump-water-heaters",
        title="The Best Hybrid Heat Pump Water Heaters",
        raw_content="Hybrid heat pumps offer up to 70% energy savings over conventional electric resistance water heaters.",
        summary="Review of leading hybrid heat pump units.",
        db_path=temp_db,
    )

    eval_id = insert_product_evaluation(
        document_id=doc_id,
        product_name="Rheem ProTerra Hybrid",
        category="Water Heating",
        verdict="Top Pick",
        pros=["High UEF rating of 3.88", "Built-in Wi-Fi & leak detection"],
        cons=["Requires condensate drain line"],
        price_point="$1,899",
        db_path=temp_db,
    )
    assert eval_id is not None

    evals = get_product_evaluations(product_name="Rheem", db_path=temp_db)
    assert len(evals) == 1
    assert evals[0]["verdict"] == "Top Pick"
    assert "High UEF rating of 3.88" in evals[0]["pros"]
