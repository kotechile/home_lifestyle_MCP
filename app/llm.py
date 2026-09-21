"""LLM summarization, entity extraction, and heuristic fallback for Home & Lifestyle intelligence."""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from openai import OpenAI

from app.config import get_config

logger = logging.getLogger(__name__)


def resolve_provider() -> str:
    """Resolve provider with automatic fallback based on available API keys."""
    explicit = os.environ.get("LLM_PROVIDER")
    if explicit:
        return explicit.lower()

    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"

    config_provider = get_config().get("llm", {}).get("provider", "openrouter").lower()
    return config_provider


def get_llm_client() -> Optional[OpenAI]:
    """Initialize OpenAI-compatible client for OpenRouter, Gemini, or OpenAI."""
    provider = resolve_provider()

    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if api_key:
            return OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )

    elif provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            return OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=api_key,
            )

    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            return OpenAI(api_key=api_key)

    # General fallback if any key exists
    if os.environ.get("OPENROUTER_API_KEY"):
        return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])
    if os.environ.get("GEMINI_API_KEY"):
        return OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=os.environ["GEMINI_API_KEY"])
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    return None


def get_model_name() -> str:
    provider = resolve_provider()
    config_model = get_config().get("llm", {}).get("model")

    if provider == "openrouter":
        return os.environ.get("LLM_MODEL", config_model or "nousresearch/hermes-3-llama-3.1-405b")
    elif provider == "gemini":
        return os.environ.get("LLM_MODEL", "gemini-2.0-flash")
    elif provider == "openai":
        return os.environ.get("LLM_MODEL", "gpt-4o-mini")
    return "mock"


def _fallback_extract(title: str, content: str, category: str = "General") -> Dict[str, Any]:
    """Deterministic extractor when no LLM API key is configured."""
    sentences = [s.strip() for s in content.split(".") if len(s.strip()) > 30]
    summary = ". ".join(sentences[:3]) + "." if sentences else title

    # Extract metrics heuristically (percentages, mortgage rates, dollars, kWh, sq ft)
    metrics = []
    pattern = (
        r"(\b\d+(\.\d+)?%\b|"
        r"\$\d+(?:,\d{3})*(?:\.\d+)?\s*(?:billion|million|M|k|K)?|"
        r"\b\d+(\.\d+)?\s*(?:kWh|kW|watts|amps|volts|sq\s*ft|square\s*feet|basis\s*points|bps)\b|"
        r"\b(?:30|15)-year\s+fixed\b)"
    )
    matches = re.finditer(pattern, content, re.IGNORECASE)
    for m in list(matches)[:5]:
        start = max(0, m.start() - 40)
        end = min(len(content), m.end() + 40)
        context = content[start:end].replace("\n", " ").strip()
        metrics.append({"metric": m.group(0), "context": f"...{context}..."})

    # Actionable takeaways from headings or key lines
    takeaways = []
    lines = [line.strip("- *#• \t") for line in content.splitlines() if len(line.strip()) > 40]
    for line in lines[:3]:
        takeaways.append(line)
    if not takeaways and sentences:
        takeaways = [sentences[0]]

    # Tag extraction based on curated residential/home keywords
    known_tags = [
        "Home Assistant", "Matter", "Thread", "Zigbee", "Z-Wave", "Wi-Fi 7", "Smart Home",
        "Solar", "Heat Pump", "Battery", "Powerwall", "EV Charging", "Electrification",
        "Mortgage Rates", "Housing Starts", "Inventory", "Home Prices", "Refinancing",
        "Renovation", "ADU", "Zoning", "Floor Plan", "Appliances", "Interior Design", "DIY"
    ]
    topics = [t for t in known_tags if re.search(rf"\b{re.escape(t)}\b", content, re.IGNORECASE)]
    if not topics:
        topics = [category]

    # Market metrics extraction
    market_metrics = []
    if "mortgage" in content.lower() or "rate" in content.lower():
        rate_match = re.search(r"(\d+\.\d{2})%", content)
        if rate_match:
            market_metrics.append({
                "metric_name": "Mortgage Interest Rate",
                "value": f"{rate_match.group(1)}%",
                "period": "Recent",
                "context": title
            })

    return {
        "summary": summary,
        "key_metrics": metrics,
        "takeaways": takeaways,
        "topics": topics,
        "market_metrics": market_metrics,
        "product_evaluations": [],
    }


def analyze_article(
    title: str,
    content: str,
    source_name: str,
    category: str = "General",
) -> Dict[str, Any]:
    """Analyze home & lifestyle article, extracting briefs, metrics, product ratings, and DIY takeaways."""
    client = get_llm_client()
    if not client:
        logger.info("No LLM API key configured; using deterministic heuristic fallback.")
        return _fallback_extract(title, content, category=category)

    truncated_content = content[:15000]

    system_prompt = (
        "You are an expert analyst in Home Technology, Residential Real Estate, Architecture, Energy Decarbonization, and DIY/Renovation.\n"
        "Analyze the provided article and extract high-signal insights for homeowners, architects, and real estate enthusiasts.\n"
        "You MUST respond ONLY with valid JSON conforming exactly to this schema:\n"
        "{\n"
        '  "summary": "Concise 2-3 paragraph executive brief with high-signal takeaways.",\n'
        '  "key_metrics": [\n'
        '    {"metric": "e.g. 6.85% 30-year fixed rate or $7,500 heat pump rebate", "context": "Brief context"}\n'
        "  ],\n"
        '  "takeaways": ["Actionable tip or key implication 1", "Actionable tip 2"],\n'
        '  "topics": ["Tag1", "Tag2"],\n'
        '  "market_metrics": [\n'
        '    {"metric_name": "e.g. Active Inventory", "value": "+12.4% YoY", "period": "Sep 2026", "context": "National inventory trends"}\n'
        "  ],\n"
        '  "product_evaluations": [\n'
        '    {"product_name": "e.g. Ecobee Smart Thermostat", "category": "Smart Climate", "verdict": "Top Pick", "pros": ["Matter support", "Remote sensor"], "cons": ["Pricey"], "price_point": "$249"}\n'
        "  ]\n"
        "}"
    )

    user_prompt = f"Source: {source_name}\nCategory: {category}\nTitle: {title}\n\nContent:\n{truncated_content}"

    try:
        response = client.chat.completions.create(
            model=get_model_name(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"} if "hermes" not in get_model_name() else None,
        )
        raw_text = response.choices[0].message.content or ""
        clean_json = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
        clean_json = re.sub(r"\s*```$", "", clean_json.strip())
        data = json.loads(clean_json)
        return {
            "summary": data.get("summary", title),
            "key_metrics": data.get("key_metrics", []),
            "takeaways": data.get("takeaways", []),
            "topics": data.get("topics", [category]),
            "market_metrics": data.get("market_metrics", []),
            "product_evaluations": data.get("product_evaluations", []),
        }
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}; falling back to heuristic extractor.")
        return _fallback_extract(title, content, category=category)
