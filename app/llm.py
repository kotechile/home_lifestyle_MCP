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
        return explicit.lower().strip().strip("'\"")

    if os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_KEY"):
        return "deepseek"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"

    config_provider = get_config().get("llm", {}).get("provider", "openrouter").lower().strip()
    return config_provider


def get_llm_client() -> Optional[OpenAI]:
    """Initialize OpenAI-compatible client for DeepSeek, OpenRouter, Gemini, or OpenAI."""
    provider = resolve_provider()

    if provider == "deepseek":
        api_key = (
            os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("DEEPSEEK_KEY")
            or os.environ.get("LLM_API_KEY")
        )
        if api_key:
            base_url = (
                os.environ.get("DEEPSEEK_BASE_URL")
                or os.environ.get("LLM_BASE_URL")
                or "https://api.deepseek.com"
            )
            return OpenAI(
                base_url=base_url,
                api_key=api_key.strip().strip("'\""),
            )

    elif provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("LLM_API_KEY")
        if api_key:
            return OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key.strip().strip("'\""),
            )

    elif provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY")
        if api_key:
            return OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=api_key.strip().strip("'\""),
            )

    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
        if api_key:
            return OpenAI(api_key=api_key.strip().strip("'\""))

    # General fallback if any key exists
    if os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_KEY"):
        base_url = os.environ.get("DEEPSEEK_BASE_URL") or os.environ.get("LLM_BASE_URL") or "https://api.deepseek.com"
        return OpenAI(
            base_url=base_url,
            api_key=(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_KEY")).strip().strip("'\""),
        )
    if os.environ.get("OPENROUTER_API_KEY"):
        return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"].strip())
    if os.environ.get("GEMINI_API_KEY"):
        return OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=os.environ["GEMINI_API_KEY"].strip())
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAI(api_key=os.environ["OPENAI_API_KEY"].strip())

    return None


def get_model_name() -> str:
    explicit_model = os.environ.get("LLM_MODEL")
    if explicit_model:
        return explicit_model.strip().strip("'\"")

    provider = resolve_provider()
    config_llm = get_config().get("llm", {})
    config_model = config_llm.get("model")
    config_provider = config_llm.get("provider", "").lower().strip()

    if provider == "deepseek":
        return config_model if config_provider == "deepseek" else "deepseek-flash"
    elif provider == "openrouter":
        return config_model or "nousresearch/hermes-3-llama-3.1-405b"
    elif provider == "gemini":
        return config_model if config_provider == "gemini" else "gemini-2.0-flash"
    elif provider == "openai":
        return config_model if config_provider == "openai" else "gpt-4o-mini"
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

    model_name = get_model_name()
    is_reasoner = "reasoner" in model_name.lower() or "r1" in model_name.lower()
    is_hermes = "hermes" in model_name.lower()

    create_kwargs: Dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    if not is_reasoner:
        create_kwargs["temperature"] = 0.2
        if not is_hermes:
            create_kwargs["response_format"] = {"type": "json_object"}

    try:
        try:
            response = client.chat.completions.create(**create_kwargs)
        except Exception as api_err:
            if "response_format" in create_kwargs and "response_format" in str(api_err).lower():
                logger.warning(f"Retrying chat completion without response_format: {api_err}")
                create_kwargs.pop("response_format", None)
                response = client.chat.completions.create(**create_kwargs)
            else:
                raise api_err

        raw_text = response.choices[0].message.content or ""

        # Remove reasoning tags like <think>...</think> (common in DeepSeek R1/reasoner)
        clean_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()

        # Find JSON block enclosed in ```json ... ``` or outermost { ... }
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean_text, flags=re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r"(\{.*\})", clean_text, flags=re.DOTALL)
            json_str = json_match.group(1) if json_match else clean_text

        data = json.loads(json_str)
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
