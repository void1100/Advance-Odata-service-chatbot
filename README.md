# Advanced OData Service Orchestration (MCP-Based)

A self-contained, locally-runnable implementation of the **Advanced OData Service Orchestration Architecture**. It connects to any OData v4 service, orchestrates queries through an LLM reasoning engine, and exposes a chat-style frontend for natural-language interaction.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Git installed
- (Optional) A free LLM API key for real AI responses (Groq or Gemini recommended)

## Clone & Run

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

### 2. (Optional) Configure an LLM API key

Create a `.env` file in the project root:

```bash
# For Groq (recommended — free tier: 14,400 requests/day)
LLM_PROVIDER=openai
OPENAI_API_KEY=gsk_your_key_here
OPENAI_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
```

Or for Gemini:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIza_your_key_here
LLM_MODEL=gemini-2.0-flash
```

Free API keys:
- Groq: https://console.groq.com/keys
- Gemini: https://aistudio.google.com/apikey

> **Note:** Without an API key, the system uses a mock LLM that echoes queries back.

### 3. Start with Docker

```bash
docker compose up -d --build
```

Wait ~30-60 seconds for all services to start.

### 4. Open the application

| Page | URL |
|------|-----|
| **Landing Page** | http://localhost:3000 |
| **Chat App** | http://localhost:3000/app/ |
| **Admin Portal** | http://localhost:3000/admin/ |
| **API Docs (Swagger)** | http://localhost:8000/docs |
| **Neo4j Browser** | http://localhost:7474 |
| **n8n Workflows** | http://localhost:5678 |

## Default Credentials

| Service | Username | Password |
|---------|----------|----------|
| Admin Portal | `admin` | `admin123!` |
| Neo4j | `neo4j` | `password` |
| n8n | `admin` | `admin` |

## Usage

### Chat App (`/app/`)

1. Type a natural language query in the input box
2. Press Enter or click **Send**
3. View results in **Table**, **Graph**, or **Analyze** tabs
4. Use **Download CSV** to export data
5. Switch LLM model using the dropdown in the sidebar

**Sample queries:**
```
Show top 5 customers from Germany
List all products in Beverages category
How many customers are in France?
Show top 5 most expensive products
Show all Airlines from trippin
Retrieve top 20 products with prices and stock from Northwind and Sample services
```

### Admin Portal (`/admin/`)

1. Login with `admin` / `admin123!`
2. Use the sidebar to navigate:
   - **Dashboard**: Overview of users, services, audit activity
   - **User Management**: Create/edit/delete users, assign roles
   - **Role Management**: 5 default roles, custom roles with granular permissions
   - **Service Management**: Register new OData services by URL
   - **Custom Entities**: Create virtual entities from real OData entities
   - **Join Services**: Join entities across different OData services
   - **Analytics**: Query volume, action breakdowns
   - **Audit Log**: All admin actions tracked
   - **Settings**: LLM provider/model, system config

### Join Services Chatbot

1. Go to **Admin Portal → Join Services**
2. Click **Execute** on a join
3. Scroll down to the **"Ask about this data"** chatbot
4. Type questions about the joined data:
   - "How many rows are from each service?"
   - "Show me only FirstName and LastName columns"
   - "Filter by source_service = trippin"

### Share Feature

1. Run a query in the chat
2. Click the **blue share button** (bottom-right)
3. Pick a channel: Email, WhatsApp, Copy, or Slack

## Features

### Chat Interface
- Natural language input with chat history
- Tabular results with sorting
- CSV export
- Session management (create, rename, delete)
- Vector memory for context from prior conversations

### Chart Visualization
- **Table**: Full data table with OData metadata filtered out
- **Graph**: Auto-detects best visualization:
  - Pie Chart (categorical data)
  - Bar Chart (numerical comparisons)
  - Network Graph (entity relationships)
- Sub-tabs for manual override (Auto/Pie/Bar/Network)

### ML Analysis (16 Algorithms)
Click the **Analyze** tab to run ML on query results:

**Unsupervised (5):**
- Summary Statistics, Anomaly Detection, Correlation, K-Means, Feature Importance

**Supervised (12):**
- Decision Tree, Random Forest, Linear Regression, Logistic Regression
- XGBoost, CatBoost, KNN, SVM, Gradient Boosting, Ada Boost, Extra Trees, Naive Bayes

**Data Cleaning Pipeline:**
- Missing values, outlier removal, normalization, encoding, deduplication

### Cross-Service Joins
- Union: Stack rows from multiple services
- Match: Join by common key
- Enrichment: Primary + secondary lookup

### Custom Entities
- Create virtual entities from real OData entities
- Auto-generates MCP tools per custom entity
- Persisted in Neo4j graph

### Authentication & Authorization
- JWT tokens with httpOnly cookies
- Password strength validation
- Account lockout after 5 failed attempts
- Role-based access control (5 default roles)
- Audit logging for all admin actions

### Dark Mode
- Toggle via sun/moon button in header
- Persists across sessions
- Auto-detects system preference

## LLM Providers

| Provider | Model | Free Tier |
|----------|-------|-----------|
| Groq | llama-3.3-70b-versatile | 14,400 RPD, 30 RPM |
| Groq | llama-3.1-8b-instant | Fastest |
| Gemini | gemini-2.0-flash | 15 RPM, 1500 RPD |
| OpenAI | gpt-4o-mini | Pay-per-use |
| Mock | Deterministic planner | Unlimited |

## Docker Services

| Service | Port | Description |
|---------|------|-------------|
| frontend | 3000 | nginx serving landing, chat, admin |
| backend | 8000 | FastAPI REST API |
| neo4j | 7474, 7687 | Graph database |
| sample-odata | 5000 | Local test OData service |
| n8n | 5678 | Workflow automation |

## Commands

```bash
# Start all services
docker compose up -d --build

# Stop all services
docker compose down

# Stop and wipe all data
docker compose down -v

# Rebuild a specific service
docker compose up -d --build backend

# View logs
docker logs odata-backend -f
docker logs odata-frontend -f

# Restart backend
docker restart odata-backend
```

## Project Structure

```
project_root/
├── backend/                       # FastAPI backend
│   ├── app/
│   │   ├── agents/                # discovery, reasoning, policy, orchestrator
│   │   ├── auth/                  # JWT auth, password hashing, RBAC, SQLite DB
│   │   ├── admin/                 # admin routes (users, roles, services, analytics)
│   │   ├── db/                    # neo4j, chroma, sqlite, in-memory graph
│   │   ├── mcp/                   # MCP tool server
│   │   ├── schemas/               # Pydantic models
│   │   ├── services/              # OData client, builder, sanitizer, manager, ML engines
│   │   ├── config.py
│   │   └── main.py
│   ├── data/                      # SQLite auth DB (persisted via volume)
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── index.html                 # Landing page
│   ├── app/                       # Chat application
│   │   ├── index.html
│   │   ├── styles.css
│   │   └── app.js
│   └── admin/                     # Admin portal
│       ├── index.html
│       ├── styles.css
│       └── app.js
├── sample_odata_service/          # Local OData v4 test service
├── n8n-workflows/                 # n8n workflow templates
├── docker-compose.yml
├── .env.example
└── README.md
```

## API Endpoints

### Chat & Analysis
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/chat` | POST | Natural-language query |
| `/analyze` | POST | Unsupervised ML analysis |
| `/ml/train` | POST | Train supervised ML model |
| `/ml/clean` | POST | Data cleaning pipeline |
| `/ml/predict` | POST | Predict using trained model |
| `/ml/algorithms` | GET | List supported algorithms |
| `/ml/models` | GET | List trained models |
| `/share` | POST | Share chat via n8n webhook |

### Services
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/services` | GET / POST | List / register OData services |
| `/services/{id}` | DELETE | Remove a service |
| `/services/{id}/refresh` | POST | Re-fetch metadata |
| `/services/health` | GET | Health check all services |

### Custom Entities & Joins
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/custom_entities` | GET | List custom entities |
| `/custom_entities/{svc}` | POST / DELETE | Create / delete custom entity |
| `/joins` | GET / POST | List / create joins |
| `/joins/{id}` | DELETE | Delete a join |
| `/joins/{id}/execute` | POST | Execute a join |
| `/joins/{id}/chat` | POST | Chat about join data |

### Auth & Admin
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/auth/login` | POST | Login |
| `/auth/logout` | POST | Logout |
| `/auth/me` | GET | Current user |
| `/admin/users` | GET / POST | List / create users |
| `/admin/roles` | GET / POST | List / create roles |
| `/admin/analytics` | GET | Query analytics |
| `/admin/audit` | GET | Audit log |
| `/admin/dashboard` | GET | Dashboard summary |

### LLM & Sessions
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/llm/config` | GET / POST | Get / set LLM provider/model |
| `/sessions` | GET / POST | Chat sessions |
| `/sessions/{id}/messages` | GET | Message history |

### MCP
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/mcp/tools` | GET | List MCP tools |
| `/mcp/call` | POST | Call an MCP tool |

## Troubleshooting

**Services won't start:**
- Ensure Docker Desktop is running
- Check ports 3000, 5000, 7474, 7687, 8000, 5678 are not in use

**LLM returns mock responses:**
- Check `.env` file exists with valid API key
- Restart backend: `docker restart odata-backend`

**Query returns 0 rows:**
- Check the service is registered: `http://localhost:8000/services`
- Try a simpler query: "Show top 5 customers"

**Admin portal shows "Authentication required":**
- Login at `http://localhost:3000/admin/` with `admin` / `admin123!`

## License

MIT
