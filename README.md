# Advanced OData Service Orchestration (MCP-Based)

A self-contained, locally-runnable implementation of the **Advanced OData
Service Orchestration Architecture** shown in the design. It connects to any
OData v4 service, orchestrates queries through an LLM reasoning engine, and
exposes a chat-style frontend for natural-language interaction.

## Quick start (Docker)

```bash
docker compose up -d --build
```

Wait ~30s for everything to start, then open **`http://localhost:3000`**.

This brings up:
- **Frontend** (nginx) at `http://localhost:3000`
- **Backend** (FastAPI) at `http://localhost:8000` (docs at `/docs`)
- **Neo4j** graph DB at `bolt://localhost:7687` (browser at `http://localhost:7474`)
- **Sample OData service** at `http://localhost:5000`
- **n8n** workflow automation at `http://localhost:5678` (admin/admin)
- A one-shot **seeder** that registers the Northwind and sample OData services

After the first build, services (including Northwind) are auto-registered.
On subsequent restarts the backend re-hydrates its in-memory service
registry from Neo4j, so the seed only needs to run once per fresh
`neo4j_data` volume.

To stop:
```bash
docker compose down
```

To wipe all data (including Neo4j):
```bash
docker compose down -v
```

## LLM Providers

The system supports multiple LLM providers. Set your preferred provider via
the UI dropdown or the API:

| Provider | Model | Free Tier |
|----------|-------|-----------|
| Groq | llama-3.3-70b-versatile | 14,400 RPD, 30 RPM |
| Gemini | gemini-2.0-flash | 15 RPM, 1500 RPD |
| OpenAI | gpt-4o-mini | Pay-per-use |
| Mock | Deterministic planner | Unlimited |

```bash
# Set Groq (recommended for free usage)
GROQ_API_KEY=gsk_... docker compose up -d

# Set Gemini
GEMINI_API_KEY=AIza... docker compose up -d

# Set OpenAI
OPENAI_API_KEY=sk-... docker compose up -d
```

Free API keys:
- Groq: https://console.groq.com/keys
- Gemini: https://aistudio.google.com/apikey

### Sample queries to try in the chat

```
Show top 5 customers from Germany
List all products in Beverages category
Show top 10 orders with status Shipped
How many customers are in France?
Show top 5 most expensive products
Show customers with their orders
```

## Features

### Chat Interface
- Natural language input with chat history
- Tabular results with sorting
- CSV export
- Session management (create, rename, delete)
- Vector memory for context from prior conversations

### Chart Visualization
Results are displayed with **Table | Graph** tabs:
- **Table**: Full data table with OData metadata columns filtered out
- **Graph**: Auto-detects best visualization from data shape
  - **Pie Chart**: Categorical data with 2-8 unique values
  - **Bar Chart**: Numerical comparisons (auto-rotates horizontal for 6+ labels)
  - **Network Graph**: Entity relationships (hub-and-spoke with force-directed layout)
- Sub-tabs (Auto/Pie/Bar/Network) for manual override
- Insights panel with reasoning and observations

### ML Analysis
Click the **Analyze** tab to run ML algorithms on query results:
- **Summary Statistics**: Mean, median, std, min/max for numeric columns
- **Anomaly Detection**: Z-score analysis (rows with z > 2 flagged)
- **Correlation Analysis**: Pearson correlation between numeric columns
- **K-Means Clustering**: Groups similar rows (k=2 or k=3)
- **Feature Importance**: Ranks columns by variance contribution

### Dark Mode
- Toggle via sun/moon button in header
- Persists across sessions
- Auto-detects system preference
- URL param: `?theme=dark`

### Service Health
- Health badges for all registered services
- Status: healthy (green), degraded (yellow), down (red)
- Latency measurement for each service

### LLM Model Switcher
- Runtime switching between 9 LLM options
- Persisted in localStorage
- Badge shows active provider (openai/groq/gemini/mock)

## Architecture

```
        Problem & Input                Orchestration Layer                  Service Execution Layer
        ───────────────                ──────────────────                  ──────────────────────
        User Interface                 Service Discovery Agent             MCP Protocol Bridge
        Natural Language Query ─►      Tool Registry (ChromaDB)            OData Request Builder
                                       Schema Store (OData CSDL)           Response Sanitizer
                                       LLM Reasoning Engine                OData Endpoints
                                       Relationship & Access Manager
                                       Graph DB (Neo4j + in-memory fallback)
                                       Authorization & Policy Engine
                                       Vector Memory (ChromaDB)
```

## Project structure

```
project_root/
├── backend/                       # FastAPI backend
│   ├── app/
│   │   ├── agents/                # discovery, reasoning, policy, orchestrator
│   │   ├── db/                    # neo4j, chroma, sqlite, in-memory graph
│   │   ├── mcp/                   # MCP tool server
│   │   ├── schemas/               # Pydantic models
│   │   ├── services/              # OData client, builder, sanitizer, manager, ML engine
│   │   ├── config.py
│   │   └── main.py
│   ├── scripts/seed_sample_service.py
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py
├── frontend/                      # Static HTML/CSS/JS chat UI
│   ├── index.html                 # Theme toggle, LLM selector, CDN scripts
│   ├── styles.css                 # Dark mode, result panels, chart styles
│   └── app.js                     # Chart renderers, ML analysis, data analyzer
├── sample_odata_service/          # A tiny local OData v4 service for testing
│   ├── app.py
│   └── requirements.txt
├── docker-compose.yml             # 5 services: frontend, backend, neo4j, sample-odata, n8n
└── README.md
```

## API Surface

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/services` | GET / POST | List / register OData services |
| `/services/{id}` | DELETE | Remove a service |
| `/services/{id}/refresh` | POST | Re-fetch metadata |
| `/services/health` | GET | Health check all services |
| `/roles` | GET | List role policies |
| `/chat` | POST | Natural-language query endpoint |
| `/analyze` | POST | Run ML analysis on table data |
| `/llm/config` | GET / POST | Get/set LLM provider and model |
| `/sessions` | GET / POST | Chat sessions |
| `/sessions/{id}` | PATCH / DELETE | Rename / delete a session |
| `/sessions/{id}/messages` | GET | Message history |
| `/mcp/tools` | GET | List MCP-style tools |
| `/mcp/call` | POST | Call an MCP-style tool |

## Using the MCP server from an MCP-compatible client

The backend exposes MCP-style tools at `/mcp/tools` and `/mcp/call`. The
included `app/mcp/mcp_server.py` also includes the tool definitions
(`list_services`, `register_service`, `query_odata`, `list_sessions`,
`get_messages`) which can be wired into a stdio MCP transport by adapting the
`call_tool` method into an MCP server entrypoint.
