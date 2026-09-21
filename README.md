# 🏡 Home, Real Estate & Lifestyle Intelligence MCP

An automated intelligence gathering pipeline and Model Context Protocol (MCP) server for **Home Improvement, Smart Living, Residential Energy, Real Estate Economics, Architecture & Zoning Policy**.

Harvests, parses, synthesizes, and indexes leading editorial publications, macro real estate data, hardware testing labs, and policy bulletins.

---

## 🏗️ Architecture

```
[Smart Tech & IoT] ────────┐
[Residential Energy] ──────┼──> Trafilatura / Jina ──> LLM Structurer (Gemini / Hermes 3) ──> SQLite (FTS5 BM25)
[Real Estate & Economy] ───┼                                                                       ▲
[Architecture & Living] ───┤                                                                       │
[Policy & Zoning] ─────────┘                                                ┌──────────────────────┴──────────────────────┐
                                                                            │ FastMCP Server (stdio / sse)               │
                                                                            │ ├── search_home_intelligence               │
                                                                            │ ├── get_latest_home_insights               │
                                                                            │ ├── get_market_and_mortgage_trends         │
                                                                            │ ├── get_product_recommendations            │
                                                                            │ ├── get_diy_and_renovation_ideas           │
                                                                            │ └── trigger_pipeline_refresh               │
                                                                            └──────────────────────▲──────────────────────┘
                                                                                                   │
                                                                                      [Claude / Cursor / Client]
```

---

## 📡 Curated Intelligence Sources & Categories

| Category | Source Name | Core Focus / Subject Matter | RSS / Feed Endpoint |
|---|---|---|---|
| **Smart Tech & IoT** | **Home Assistant Blog** | Local-first automations, Matter/Thread, and core ecosystem updates | `https://www.home-assistant.io/atom.xml` |
| **Smart Tech & IoT** | **The Verge (Smart Home)** | Mainstream protocol announcements, device rollouts, and consumer tech reviews | `https://www.theverge.com/smart-home/rss/index.xml` |
| **Smart Tech & IoT** | **Ars Technica (Gadgets)** | Home networking hardware, Wi-Fi performance, security, and smart devices | `https://feeds.arstechnica.com/arstechnica/gadgets` |
| **Smart Tech & IoT** | **Automate Your Life** | Independent tutorials, sensor deployments, and smart home hardware testing | `https://automateyourlife.net/feed/` |
| **Residential Energy** | **Electrek (Energy)** | Residential solar, home battery storage systems, and EV bidirectional charging | `https://electrek.co/guides/energy/feed/` |
| **Residential Energy** | **Canary Media** | Residential decarbonization, heat pump adoption, and utility rate structures | `https://www.canarymedia.com/rss` |
| **Residential Energy** | **CleanTechnica (Solar)** | Rooftop solar policy, residential battery setups, and state clean-energy rebates | `https://cleantechnica.com/category/solar-power/feed/` |
| **Real Estate & Economy** | **Calculated Risk** | Macro housing data, inventory tracking, mortgage performance, and housing starts | `https://www.calculatedriskblog.com/feeds/posts/default` |
| **Real Estate & Economy** | **Wolf Street (Housing)** | Data-driven market analysis, housing valuation shifts, and mortgage rate trends | `https://wolfstreet.com/category/all/housing-bubble/feed/` |
| **Real Estate & Economy** | **Redfin Data Center** | Regional pricing shifts, buyer/seller demand metrics, and migration patterns | `https://www.redfin.com/news/feed/` |
| **Real Estate & Economy** | **Mortgage News Daily** | Daily mortgage rate tracking, bond yield impacts, and lending policy changes | `https://www.mortgagenewsdaily.com/rss/news` |
| **Architecture & Living** | **Dwell** | Modern residential layouts, ADU blueprints, floor plan optimization, and additions | `https://www.dwell.com/feed` |
| **Architecture & Living** | **Dezeen (Residential)** | High-end architectural case studies, structural renovations, and material innovations | `https://www.dezeen.com/architecture/residential/feed/` |
| **Architecture & Living** | **Remodelista** | Interior workspace design, architectural fittings, and high-quality home finishes | `https://www.remodelista.com/feed/` |
| **Architecture & Living** | **Wirecutter (Home)** | Long-term reliability testing on major appliances, tools, and home gear | `https://www.nytimes.com/wirecutter/feed/` |
| **Policy & Urban Planning** | **Planetizen** | Nationwide single-family zoning reforms, ADU legislation, and land-use laws | `https://www.planetizen.com/rss.xml` |
| **Policy & Urban Planning** | **Bloomberg CityLab** | Urban/suburban housing policy, infrastructure investments, and local tax trends | `https://www.bloomberg.com/citylab/rss` |

### 📂 OPML Feed Import
An exportable `feeds.opml` file is included at the root of the repository. You can import it directly into RSS readers like **NetNewsWire**, **Feedly**, or **Inoreader**.

---

## 🚀 Quick Start

### 1. Environment Setup
```bash
cd "HOME LIFESTYLE MCP"

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and insert your LLM API key (OpenRouter / OpenAI / Gemini)
```

### 2. Initialize Database & Run Ingestion
```bash
# Initialize SQLite database schema and FTS5 indexes
python -m app.cli init-db

# Run full ingestion across all 17 feeds
python -m app.cli run-all

# Or crawl by category:
python -m app.cli crawl-feeds --category "Smart Tech"
python -m app.cli crawl-feeds --category "Energy"
python -m app.cli crawl-feeds --category "Housing"
python -m app.cli crawl-feeds --category "Architecture"
python -m app.cli crawl-feeds --category "Policy"
```

### 3. Query via CLI
```bash
# Full-text BM25 search
python -m app.cli search "Matter 1.3"
python -m app.cli search "heat pump rebate" --category "Residential Energy"

# Query macro housing and mortgage trends
python -m app.cli market-trends --topic "Mortgage"

# Query tested appliance & smart home gear picks
python -m app.cli gear-picks --category "Appliances"

# Database health & stats
python -m app.cli stats
```

---

## 🔌 Connecting to MCP Clients (Claude Desktop, Cursor, etc.)

### Local Development (stdio)
Add this to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "home-lifestyle-intel": {
      "command": "/Users/jorgefernandezilufi/Documents/_article_research/HOME LIFESTYLE MCP/.venv/bin/python",
      "args": [
        "-m", "app.mcp_server"
      ]
    }
  }
}
```

### Remote Stdio over SSH (VPS Deployment)
```json
{
  "mcpServers": {
    "home-lifestyle-intel": {
      "command": "ssh",
      "args": [
        "-i", "~/.ssh/id_rsa",
        "root@your-vps-ip",
        "/opt/home-lifestyle-mcp/.venv/bin/python",
        "-m", "app.mcp_server"
      ]
    }
  }
}
```

---

## 🛠️ FastMCP Tools Reference

1. `search_home_intelligence(query, category, limit)`: Full-text search across all home, renovation, smart tech, energy, and real estate documents.
2. `get_latest_home_insights(category, days_back, limit)`: Recent articles filterable by category (Smart Tech, Energy, Housing, Architecture, Policy).
3. `get_market_and_mortgage_trends(topic, limit)`: Macro housing inventory, mortgage rate trends, and price shifts.
4. `get_product_recommendations(category, product_name, limit)`: Tested smart devices, home appliances, and solar/battery picks from Wirecutter, Verge, etc.
5. `get_diy_and_renovation_ideas(topic, limit)`: Floor plan inspirations, ADU blueprints, interior hardware, and renovation guides.
6. `trigger_pipeline_refresh(category)`: On-demand background crawl.
7. `get_pipeline_stats()`: Database metrics, counts, and category distribution.

---

## 🌐 HTTP Endpoints (n8n & Coolify)

When deployed via Docker / Uvicorn, the following HTTP routes are available:

- `GET /health` — Health check endpoint for Coolify
- `GET /api/stats` — Database statistics JSON
- `GET /api/insights/recent?days_back=7&limit=10` — JSON feed for automated n8n digests
- `POST /api/crawl?category=all&max=10` — Webhook endpoint to trigger crawls via cron or n8n
