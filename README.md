# Planet Material Labs — AI Research Assistant

> An autonomous, AI-powered materials science research platform built for **Planet Material Labs**. It ingests technical datasheets and research papers, extracts structured material properties using local LLMs, maintains a semantic knowledge base with a NetworkX graph layer, drives an autonomous Bayesian-optimised experiment loop, provides a RAG-powered chat interface, and exposes a full digital twin / GP surrogate for formulation space exploration — all running 100% offline on local hardware.

**Current build state: Phases 1–7 complete. Phase 8 (model routing) partially implemented.**

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [System Architecture](#3-system-architecture)
4. [How It Works — End to End](#4-how-it-works--end-to-end)
5. [Backend Module Reference](#5-backend-module-reference)
6. [Frontend Component Reference](#6-frontend-component-reference)
7. [Qdrant Schema — 9 Collections](#7-qdrant-schema--9-collections)
8. [Data & Ingestion Pipeline](#8-data--ingestion-pipeline)
9. [Autonomous Research Loop](#9-autonomous-research-loop)
10. [Bayesian Optimisation & GP Surrogate](#10-bayesian-optimisation--gp-surrogate)
11. [Digital Twin](#11-digital-twin)
12. [Chat System](#12-chat-system)
13. [API Reference](#13-api-reference)
14. [Project Phases](#14-project-phases)
15. [Setup & Running](#15-setup--running)
16. [Directory Structure](#16-directory-structure)
17. [Known Limitations & Design Decisions](#17-known-limitations--design-decisions)

---

## 1. Project Overview

Planet Material Labs is developing AI tooling to accelerate materials research. This assistant is the first internal platform — it replaces manual, spreadsheet-driven property lookup and hypothesis generation with a fully automated pipeline.

**What it does end-to-end:**

```
PDF Upload → Text Extraction → LLM Property Extraction → Qdrant Storage
      ↓
Semantic Search + Knowledge Graph (NetworkX + PageRank)
      ↓
Autonomous Experiment Loop (Goal → BO Acquisition → GP Predict → Score → Approve → Next)
      ↓
Digital Twin (GP Oracle → Virtual Runs → 2D Space Maps)
      ↓
RAG Chat (5 roles: Material Expert / Technical Reviewer / Literature Researcher /
          Document Parser / Compliance Auditor) + optional Tavily web search
```

**Hardware target:** Windows 11, NVIDIA RTX 3050 (4GB VRAM), 16GB RAM. Everything runs locally — no data leaves the machine. Tavily web search is optional and requires an API key.

---

## 2. Technology Stack

| Layer | Technology | Version / Notes |
|---|---|---|
| Frontend framework | React 18 | via Vite |
| Frontend bundler | Vite | Browser-based dev server and production build |
| Styling | Pure CSS (custom design system) | Electric Indigo glassmorphism palette |
| Icons | lucide-react | — |
| Charts | Recharts | ResultsPanel and surrogate visualisations |
| Backend framework | FastAPI | Python 3.11+ |
| ASGI server | Uvicorn | — |
| LLM runtime | Ollama | localhost:11434, CUDA-accelerated |
| LLM — extraction | `qwen2.5:3b-instruct-q4_K_S` | Fast structured JSON extraction from PDFs |
| LLM — chat | `qwen2.5:7b-instruct-q4_K_S` | RAG chat responses |
| LLM — orchestrator | `qwen2.5:3b-instruct-q4_K_M` | Hypothesis generation |
| Embedding model | `nomic-embed-text` | 768-dimensional vectors |
| Vector database | Qdrant | localhost:6333 or local on-disk storage |
| Knowledge graph | NetworkX | In-memory, rebuilt from Qdrant every 300s |
| GP surrogate | BoTorch + GPyTorch | Gaussian Process models for property prediction |
| Safe expression eval | SymPy | Custom scoring expressions in digital twin |
| Web search | Tavily Python SDK | Optional; requires API key in settings |
| PDF parsing | pdfplumber + PyMuPDF | Fallback chain |
| LangChain | `langchain-ollama`, `langchain-qdrant`, `langchain-text-splitters`, `langchain-community` | Used in bulk_parser.py, qdrant_store.py |

---

## 3. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        REACT FRONTEND  :5173                         │
│                                                                      │
│  Sidebar   GoalPanel   KnowledgePanel   ExperimentDashboard          │
│  PapersView  ExperimentsPanel (Kanban)  ChatPanel  DecisionPanel     │
│  ResultsPanel  DocumentDetails  SchemaBuilder  SettingsPanel         │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ HTTP / SSE  (localhost:8000)
┌────────────────────────────▼─────────────────────────────────────────┐
│                        FASTAPI BACKEND  :8000                        │
│                                                                      │
│  main.py ──────── REST + SSE API surface (+ twin_routes.py router)   │
│  │                                                                   │
│  ├── job_queue.py ─── Priority queue, background worker thread       │
│  │       └── process_job()                                           │
│  │             ├── parser.py      (PDF → raw text)                   │
│  │             ├── extractor.py   (text → JSON schema via LLM)       │
│  │             └── qdrant_store.py (upsert to all collections)       │
│  │                                                                   │
│  ├── orchestrator.py ── Autonomous loop state machine (HITL)         │
│  │       ├── experiment_runner.py (predict + composite score)        │
│  │       └── surrogate/loop.py   (BO acquisition + GP retrain)       │
│  │                                                                   │
│  ├── twin_routes.py ── Digital twin endpoints                        │
│  │       └── twin.py (interactive_predict, virtual_run, space_map)  │
│  │             └── surrogate/ (GP model, registry, DoE, encoder)     │
│  │                                                                   │
│  ├── chat.py ──────── RAG chat + roles + memory + web search         │
│  │       ├── knowledge_graph.py (graph_aware_search)                 │
│  │       ├── web_search.py (Tavily)                                  │
│  │       └── compliance_personas.py (custom auditor roles)           │
│  │                                                                   │
│  ├── knowledge_graph.py ── NetworkX + PageRank re-ranking            │
│  ├── qdrant_store.py ─── Single storage layer (all 9 collections)    │
│  ├── cache.py ──────────── Two-tier LRU/TTL cache (L1 mem + L2 disk) │
│  └── settings_store.py ─── Runtime settings (API keys, feature flags)│
└────────────────────────────┬─────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────────┐
│                    QDRANT  :6333  (local on-disk fallback)           │
│                                                                      │
│  documents · doc_chunks · material_properties · experiments          │
│  knowledge_edges · scanned_folders · job_status · chat_sessions      │
│  experiment_schemas                                                  │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────────┐
│                    OLLAMA  :11434  (CUDA)                             │
│                                                                      │
│  qwen2.5:3b-instruct-q4_K_S   (extraction — fast, structured JSON)  │
│  qwen2.5:7b-instruct-q4_K_S   (chat — better reasoning quality)     │
│  qwen2.5:3b-instruct-q4_K_M   (orchestrator — creative hypotheses)  │
│  nomic-embed-text              (embeddings — 768-dim)                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. How It Works — End to End

### Document upload → property extraction

```
Browser → POST /api/documents/upload
  → job_queue: create_job() → queue_job()
  → background worker: process_job()
      → parser.extract_text()             # pdfplumber → PyMuPDF fallback
      → extractor.extract_from_text()     # qwen2.5:3b → JSON schema
      → extractor.extract_properties_list()
      → qdrant_store.upsert_document()    # documents collection
      → qdrant_store.upsert_property() ×N # material_properties
      → qdrant_store.upsert_chunks()      # doc_chunks (768-dim vectors)
      → knowledge_graph.auto_extract_edges() # NetworkX graph update
  → Browser polls GET /api/jobs/{job_id}/stream (SSE)
```

### RAG chat message

```
Browser → POST /api/chat
  → chat.py: _rephrase_query()            # resolve pronouns via LLM (if needed)
  → knowledge_graph.graph_aware_search()  # vector + PageRank + connectivity
  → (optional) web_search.search_tavily() # Tavily web results merged in
  → build prompt with context + role system prompt
  → llm.client.generate(model=CHAT_MODEL) # qwen2.5:7b
  → _strip_thinking()                     # remove <thinking> XML tags
  → ChatSession._save_to_qdrant()         # persist to chat_sessions
```

### Autonomous loop iteration

```
POST /api/loop/start (goal, weights, schema_id?)
  → orchestrator._retrieve_context()     # graph_aware_search for relevant materials
  → orchestrator._generate_candidates()  # LLM (ORCHESTRATOR_MODEL) → 3 configs
    or orchestrator._bo_candidates()     # BO acquisition → 5 configs if schema set
  → orchestrator._score_candidates()     # GP predictions + composite score
  → orchestrator._generate_decision()    # LLM reasoning + next hypothesis
  → orchestrator._persist()              # upsert_experiment() to Qdrant
  → state: AWAITING_APPROVAL
  → POST /api/loop/approve → repeat
```

---

## 5. Backend Module Reference

### `config.py`
Central configuration — all URLs, paths, collection names, model identifiers, and tuning parameters loaded from `config.yaml`. Supports hot-reload via `reload_config()`.

**Per-task model routing (from `config.yaml`):**
```yaml
llm.models.extraction:   qwen2.5:3b-instruct-q4_K_S   # fast structured JSON
llm.models.chat:         qwen2.5:7b-instruct-q4_K_S   # better reasoning quality
llm.models.orchestrator: qwen2.5:3b-instruct-q4_K_M   # creative hypotheses
llm.models.embedding:    nomic-embed-text              # 768-dim vectors
```

### `main.py`
FastAPI application. Registers all routes (including `twin_router`), starts the job queue worker on startup. All configuration is driven by `config.yaml` — CORS origins, port, model names.

### `twin_routes.py`
FastAPI `APIRouter` mounted at `/api/twin`. Exposes all Digital Twin endpoints. Registered in `main.py` via `app.include_router(twin_router)`.

### `parser.py`
PDF → plain text. Uses `pdfplumber` as primary, falls back to `PyMuPDF`. No OCR — scanned-only PDFs return empty string with a logged warning.

### `extractor.py`
LLM-based structured extraction using `qwen2.5:3b` (fast). Two schemas:

| Mode | LLM Output |
|---|---|
| TDS | `material_name`, `extraction_confidence`, `properties[]`, `processing_conditions[]` |
| Paper | `extraction_confidence`, `material_properties_mentioned[]`, `key_findings[]`, `methodology`, `research_objective` |

### `llm.py`
Ollama HTTP client with connection pooling. `get_client()` returns a singleton instance. Supports `generate()` with `json_mode=True` for structured outputs.

### `qdrant_store.py`
Single storage abstraction for all 9 Qdrant collections. All config constants (`EMBED_DIM`, `CHUNK_SIZE_CHARS`, `CHUNK_OVERLAP_CHARS`) read from `config.py` — configurable via `config.yaml`. Embedding uses `OllamaEmbeddings` from LangChain with a two-tier disk cache.

### `qdrant_mgr.py`
Higher-level search wrapper used by `chat.py`. Delegates to `knowledge_graph.graph_aware_search()` with a legacy fallback to the `parsed_materials` collection.

### `job_queue.py`
In-process priority queue with a single background worker thread.

**Priority tiers (by file size):**
- HIGH: < 1 MB
- MEDIUM: 1–10 MB
- LOW: > 10 MB

Jobs are persisted to the `job_status` Qdrant collection so they survive backend restarts.

### `orchestrator.py`
Autonomous research loop state machine.

**States:** `idle → running → awaiting_approval → (loop | stopped)`

Uses `ORCHESTRATOR_MODEL` (`qwen2.5:3b-M`) for hypothesis generation. Supports two candidate generation modes:
- **Standard**: LLM generates 3 candidates from goal + context
- **BO mode**: Acquisition function (EI) suggests 5 candidates when a schema is attached

### `experiment_runner.py`
- `predict_properties()` — pulls Qdrant context, builds prediction prompt, returns property values
- `calculate_composite_score()` — normalises predictions against schema targets, applies goal weights
- `suggest_next_configuration()` — post-completion suggestions

### `knowledge_graph.py`
NetworkX-backed directed graph over Qdrant data (rebuild TTL: 300s). Re-ranks search results:
```
final_score = 0.6 × vector_score + 0.3 × PageRank + 0.1 × connectivity
```

### `chat.py`
RAG chat engine with 5 built-in roles + dynamic compliance auditor roles. Uses `CHAT_MODEL` (`qwen2.5:7b`). Features:
- **6B**: Query rephrasing (pronoun resolution before Qdrant search)
- **6C**: `<thinking>` tag stripping from LLM output
- **6D**: 10-turn memory with 3000-char soft budget
- **6E**: Document Parser role (extraction quality auditor)
- **6F**: Source citations (filename + chunk preview + score)
- **6G**: Tavily web search integration (optional, auto-triggered on recency/discovery cues)

### `compliance_personas.py`
Built-in and custom compliance auditor personas (ISO-Mechanical, IEC-EMI, Nanocomposite-Reporting). Loaded into the chat system as a dynamic role. Supports CRUD via the `/api/compliance` endpoints.

### `settings_store.py`
Runtime settings store (Tavily API key, `web_search_enabled`). Persisted to `data/settings.json`. Read at request time so changes take effect immediately without restart.

### `web_search.py` / `web_crawler.py`
Tavily search returning URLs, then `web_crawler.py` scrapes and formats the HTML content for inclusion in the RAG context.

### `cache.py`
Two-tier LRU/TTL cache:
- **L1**: In-memory `InMemoryCache` with true LRU eviction (most recently accessed entries stay longest)
- **L2**: Disk-based `DiskCache` (SHA-256 keyed JSON files)

Used for: embedding vectors, LLM responses, PageRank scores, stats.

### `surrogate/` package
BoTorch Gaussian Process surrogate for Bayesian optimisation.

| Module | Responsibility |
|---|---|
| `schema.py` | `ExperimentSchema` — parameters, properties, constraints definition |
| `encoder.py` | Parameter normalisation (continuous/categorical → [0,1]) |
| `model.py` | `SurrogateModel` — BoTorch `SingleTaskGP` wrapper, predict with uncertainty |
| `registry.py` | `SurrogateRegistry` — load/cache/invalidate GP models per schema |
| `doe.py` | Latin Hypercube sampling for initial design of experiments |
| `acquisition.py` | Expected Improvement (EI) acquisition function |
| `loop.py` | `bo_iteration()` — single BO step: DoE or acquisition → candidates; `record_approval()` — adds approved point to GP training data |
| `literature_seed.py` | Seeds the GP with synthetic training points extracted from indexed literature |

### `twin.py`
Digital twin functions used by `twin_routes.py`:
- `interactive_predict()` — GP prediction for a given composition (optionally blended with a simulation hook)
- `virtual_run()` — N BO iterations using the GP as the oracle (sandbox mode)
- `space_map()` — 2D grid of GP predictions over two parameter dimensions (heatmap data)

### `custom_objective.py`
SymPy-based safe evaluation of user-defined scoring expressions. Falls back to regex-guarded `eval()` if SymPy is unavailable.

### `sim_hook.py`
Subprocess-based simulation hook runner. Executes an external script with a composition JSON and returns property predictions. Used to blend real simulation results with GP predictions in the digital twin.

### `bulk_parser.py`
Async folder-level batch ingestion using LangChain document loaders + `RecursiveCharacterTextSplitter`. Streams SSE progress events.

### `crawler.py`
Recursive folder scanner with SHA-256 dedup against the `documents` collection.

### `startup.py`
One-time Qdrant collection initialisation. Run if Qdrant is freshly installed.

### `refresh_system.py`
Dev utility — kills backend processes, wipes Qdrant collections, clears uploads folder for a clean reset.

---

## 6. Frontend Component Reference

All components in `src/components/`. React 18, no external state management — prop drilling from `App.jsx`, local `useState` elsewhere.

### `App.jsx`
Root. Owns: `activeNav`, `sidebarCollapsed` (localStorage), `loopState` (polled 10s), `counts` (polled 30s).

### `Sidebar.jsx`
Collapsible navigation. Expanded: 220px / Collapsed: 56px. CSS width transition. State in localStorage.

### `GoalPanel.jsx`
Research goal input + weight sliders (Strength / Flexibility / Cost) + loop controls (Start / Run Once / Stop). Shows current step and iteration counter.

### `KnowledgePanel.jsx`
Knowledge graph summary. Shows indexed papers and graph-extracted insights. (Currently uses mock data — wiring to `/api/graph/materials` is a known pending item.)

### `ExperimentDashboard.jsx`
Compact experiment overview in Research view. Clicking a row opens `ResultsPanel` scoped to that experiment.

### `ExperimentsPanel.jsx`
3-column Kanban board (Queued / Running / Completed). `ExperimentDetailModal` includes: conditions, results table, "Add Result" form, AI Predict, Suggest Next Config, Complete, Delete.

### `ResultsPanel.jsx`
Recharts bar and line charts. Predicted vs actual property values across iterations.

### `DecisionPanel.jsx`
Loop step progress bar + candidate list + reasoning text (inline-editable) + Approve / Stop buttons.

### `PapersView.jsx`
Document library. Single PDF upload, folder upload (`webkitdirectory`), path scan. Documents table with bulk delete (checkbox + header button). Job queue panel (live status, priority, elapsed time).

### `DocumentDetails.jsx`
Document inspection modal — 6 tabs: Overview, Properties, Methodology, Key Findings, Limitations, Raw Data. Re-extract button.

### `SchemaBuilder.jsx`
Experiment schema designer. Define parameters (name, type, range), properties (target values, units), and constraints. Saves to `/api/schemas`. Schemas attach to the autonomous loop for BO mode.

### `SettingsPanel.jsx`
Runtime settings UI. Tavily API key input (masked), web search toggle. Calls `/api/settings`.

### `ChatPanel.jsx`
RAG chat. Role selector (5 roles + compliance standards). SSE streaming responses. Session history. Web search indicator.

### `CyberLoader.jsx`
Animated startup loading screen while backend connection is being established.

---

## 7. Qdrant Schema — 9 Collections

All collections use **flat payloads** — no nested `metadata` key.

### `documents` — Document manifest
| Field | Type | Description |
|---|---|---|
| `doc_id` | string | UUID |
| `filename` | string | Original filename |
| `file_hash` | string | SHA-256 (dedup) |
| `doc_type` | string | `"tds"` or `"paper"` |
| `material_name` | string | Extracted material name |
| `properties_count` | int | Extracted property rows |
| `extraction_confidence` | float | 0.0–1.0 |
| `methodology` | string | Research methodology (papers) |
| `research_objective` | string | Research objective (papers) |
| `key_findings` | JSON string | List of key findings |
| `processing_conditions` | JSON string | List of processing conditions |
| `created_at` | ISO datetime | — |

Vector: 768-dim embedding of `filename + material_name`.

### `doc_chunks` — Text chunks (primary RAG search target)
| Field | Type | Description |
|---|---|---|
| `doc_id` | string | Parent document |
| `chunk_index` | int | Position in document |
| `content` | string | ~2000-char text chunk |
| `filename` | string | Parent filename |
| `doc_type` | string | Inherited |

Vector: 768-dim `nomic-embed-text` embedding. This is the collection searched during RAG.

### `material_properties` — Structured property rows
| Field | Type | Description |
|---|---|---|
| `doc_id` | string | Parent document |
| `property_name` | string | e.g. `"Tensile Strength"` |
| `value` | any | Numeric or string |
| `unit` | string | e.g. `"MPa"` |
| `confidence` | float | LLM extraction confidence |
| `context` | string | Test standard or note |

### `experiments` — Loop results
| Field | Type | Description |
|---|---|---|
| `exp_id` | string | UUID |
| `name` | string | e.g. `"Loop Iteration 3"` |
| `goal` | string | Research goal text |
| `iteration` | int | Loop iteration number |
| `material_name` | string | Target material |
| `candidates` | JSON | All scored candidates |
| `best_candidate` | JSON | Winning candidate with predictions |
| `reasoning` | string | LLM decision reasoning |
| `composite_score` | float | 0–1 |
| `schema_id` | string | Attached schema (BO mode) |
| `surrogate_predictions` | JSON | GP mean/std predictions |
| `acquisition_score` | float | EI acquisition value |
| `status` | string | `pending / completed` |
| `created_at` | ISO datetime | — |

### `knowledge_edges` — Graph edges
| Field | Type | Description |
|---|---|---|
| `source` | string | Source node |
| `target` | string | Target node |
| `edge_type` | string | `HAS_PROPERTY / IMPROVES / DEGRADES / SIMILAR_TO / MEASURED_BY / CONTAINS` |
| `weight` | float | Edge strength |

### `experiment_schemas` — BoTorch GP schemas
| Field | Type | Description |
|---|---|---|
| `schema_id` | string | UUID |
| `name` | string | Schema name |
| `material_system` | string | e.g. `"EPDM rubber"` |
| `parameters` | JSON | List of `{name, type, min, max, categories[]}` |
| `properties` | JSON | List of `{name, unit, target_min, target_max}` |
| `constraints` | JSON | Optional constraint expressions |
| `created_by` | string | User identifier |
| `created_at` | ISO datetime | — |

### `scanned_folders`, `job_status`, `chat_sessions`
As previously documented. `job_status` tracks ingestion jobs; `chat_sessions` stores full conversation history.

---

## 8. Data & Ingestion Pipeline

### File types supported
- `.pdf` — primary (pdfplumber + PyMuPDF fallback)
- `.docx`, `.doc` — supported by crawler, limited direct upload support

### Deduplication
SHA-256 hash checked against all hashes in `documents` before queuing. Duplicates silently skipped.

### Chunking
- Chunk size: **2000 characters** (~512 tokens)
- Overlap: **200 characters**
- Each chunk embedded independently with `nomic-embed-text`
- Values driven by `config.yaml` (`documents.chunking`)

### LLM extraction
Extraction uses `qwen2.5:3b-instruct-q4_K_S` for speed. Document text is fed in chunks of up to 4000 characters (configurable). Temperature is 0.0 for deterministic JSON output. Malformed JSON triggers a simplified retry prompt.

### Priority queue
Single daemon thread. Min-heap on `(priority.value, created_at)`. Persisted to Qdrant.

---

## 9. Autonomous Research Loop

### State machine
```
IDLE → start_loop(goal, weights, schema_id?)
  → RUNNING
       Step 0: Retrieve  (graph_aware_search)
       Step 1: Generate  (LLM candidates OR BO acquisition)
       Step 2: Predict   (GP surrogate OR experiment_runner)
       Step 3: Decide    (composite score → best candidate)
       Step 4: Approve   (pause for human review)
  → AWAITING_APPROVAL
       approve() → RUNNING (next iteration)
       stop()    → STOPPED
```

### Composite score
```
score = Σ (property_score_i × weight_i)
```
Default weights: strength=0.50 / flexibility=0.35 / cost=0.15. User-configurable in GoalPanel.

### Human-in-the-loop controls
- **Approve** — accept decision, run next iteration
- **Edit hypothesis** — modify LLM-generated text before next run
- **Stop** — halt (state preserved in memory for session)
- **Run Once** — single iteration without entering continuous mode

---

## 10. Bayesian Optimisation & GP Surrogate

When an `ExperimentSchema` is attached to the loop (`schema_id` set), the system switches to BO mode:

### Design of Experiments (cold start)
When fewer than `surrogate.min_training_points` (default: 3) approved experiments exist, the system uses **Latin Hypercube Sampling** (`surrogate/doe.py`) to generate space-filling candidates.

### Literature seeding
`surrogate/literature_seed.py` extracts synthetic training points from indexed papers to pre-warm the GP before any real experiments have been run.

### Gaussian Process model
`surrogate/model.py` wraps BoTorch's `SingleTaskGP`. Each property gets an independent GP. Predictions return `{mean, std}` per property. The `SurrogateRegistry` (`surrogate/registry.py`) caches trained models in memory and on disk.

### Acquisition function
Expected Improvement (EI) is used to select the next candidate composition. The acquisition function balances exploitation (near known optima) vs exploration (high uncertainty regions).

### Retraining
When a loop iteration is approved, `record_approval()` adds the composition + observed property values to the GP training set and triggers an async retrain. This keeps the surrogate current without blocking the loop.

---

## 11. Digital Twin

The digital twin exposes the GP surrogate as an interactive exploration tool — independent of the autonomous loop.

### Endpoints

| Endpoint | What it does |
|---|---|
| `POST /api/twin/{schema_id}/predict` | Instant GP prediction for a composition (optionally blended with a simulation hook script) |
| `POST /api/twin/{schema_id}/virtual-run` | N BO iterations using the GP as the oracle (sandbox — no real experiments) |
| `POST /api/twin/{schema_id}/space-map` | 2D grid of GP predictions over two parameters (heatmap data for the frontend) |
| `POST /api/twin/objective/validate` | Validate a custom SymPy scoring expression |
| `POST /api/twin/hook/test` | Test an external simulation script with a sample composition |
| `GET /api/twin/{schema_id}/training-data` | All approved training points (for space map overlay) |

### Custom objectives
Users can write scoring expressions like `tensile_strength * 0.6 + elongation * 0.4` using any property name from the schema. SymPy validates and evaluates these safely.

### Simulation hooks
An external Python or executable script can be pointed at via `sim_hook_path`. The twin calls it as a subprocess with the composition JSON, reads back property values, and blends them with the GP prediction.

---

## 12. Chat System

### Retrieval pipeline
1. If the query contains coreference words (`it`, `they`, `this`, etc.) and is < 150 chars: rephrase via LLM first
2. Embed rephrased query with `nomic-embed-text`
3. `knowledge_graph.graph_aware_search()` — cosine search on `doc_chunks` + PageRank re-ranking
4. (Optional) Tavily web search — triggered if enabled and query matches recency/discovery cues
5. Merge context; build role-specific prompt

### Roles
| Role | Focus |
|---|---|
| `material-expert` | Technical property analysis, standards (ISO/ASTM/UL), grade comparisons |
| `technical-reviewer` | QA, compliance gaps, inconsistencies, red flags |
| `literature-researcher` | Paper synthesis, key findings, methodology comparison |
| `document-parser` | Extraction quality audit — missing units, implausible values, low confidence |
| `compliance-auditor` | Standards compliance report using a selected compliance persona |

### Compliance personas
Built-in: `ISO-Mechanical`, `IEC-EMI`, `Nanocomposite-Reporting`. Custom personas can be added via `/api/compliance` and appear in the ChatPanel role selector.

### Memory
- Last **10 turns** (20 messages) in LLM context, soft-capped at 3000 characters
- Full session persisted to `chat_sessions` Qdrant collection
- `<thinking>` XML tags stripped from all LLM output before delivery

---

## 13. API Reference

All routes at `http://localhost:8000`.

### Documents
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/documents/upload` | Upload single PDF |
| `GET` | `/api/documents` | List all documents |
| `GET` | `/api/documents/{id}` | Get document with full payload + properties |
| `DELETE` | `/api/documents/{id}` | Delete document |
| `POST` | `/api/documents/bulk-delete` | Delete list of IDs |
| `POST` | `/api/documents/{id}/reprocess` | Re-run LLM extraction |
| `POST` | `/api/documents/reprocess-all` | Queue all zero-property docs for re-extraction |
| `GET` | `/api/documents/{id}/properties` | Get extracted properties |
| `GET` | `/api/documents/{id}/extraction` | Get extraction metadata |

### Bulk Ingestion
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/bulk-parse` | SSE-streamed folder batch parse |
| `POST` | `/api/bulk-scan` | Queue all files in a folder |
| `POST` | `/api/bulk-scan-recursive` | SSE-streamed recursive folder scan |
| `POST` | `/api/bulk-scan-ui` | Queue files from the uploads directory |
| `POST` | `/api/bulk-delete-manifest` | Clear bulk parse manifest for a folder |

### Jobs
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/jobs` | List all jobs |
| `GET` | `/api/jobs/{id}` | Get single job |
| `GET` | `/api/jobs/{id}/stream` | SSE job progress stream |
| `DELETE` | `/api/jobs/{id}` | Cancel job |
| `POST` | `/api/jobs/cancel-all` | Cancel all pending jobs |

### Experiments
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/experiments` | List experiments |
| `POST` | `/api/experiments` | Create experiment |
| `GET` | `/api/experiments/{id}` | Get experiment detail |
| `PUT` | `/api/experiments/{id}` | Update experiment with actual output |
| `DELETE` | `/api/experiments/{id}` | Delete experiment |
| `POST` | `/api/experiments/{id}/results` | Persist test results |
| `POST` | `/api/experiments/{id}/predict` | LLM property prediction |
| `POST` | `/api/experiments/{id}/suggest` | Next config suggestions |
| `POST` | `/api/experiments/{id}/complete` | Mark completed |
| `GET` | `/api/experiments/{id}/history` | Full iteration history |
| `GET` | `/api/experiments/{id}/surrogate` | GP predictions for this experiment |

### Research Loop
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/loop/status` | Current loop state |
| `POST` | `/api/loop/start` | Start/reset loop |
| `POST` | `/api/loop/iterate` | Run single iteration |
| `POST` | `/api/loop/approve` | Approve + continue |
| `POST` | `/api/loop/stop` | Stop loop |
| `PUT` | `/api/loop/hypothesis` | Edit pending hypothesis |

### Schemas (BO)
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/schemas` | Create experiment schema |
| `GET` | `/api/schemas` | List all schemas |
| `GET` | `/api/schemas/{id}` | Get schema |
| `PUT` | `/api/schemas/{id}` | Update schema |
| `DELETE` | `/api/schemas/{id}` | Delete schema |

### Surrogate / GP
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/surrogate/{schema_id}/retrain` | Force GP retrain |
| `GET` | `/api/surrogate/{schema_id}/status` | GP training status |

### Digital Twin
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/twin/{schema_id}/predict` | GP prediction for composition |
| `POST` | `/api/twin/{schema_id}/virtual-run` | N BO sandbox iterations |
| `POST` | `/api/twin/{schema_id}/space-map` | 2D property heatmap data |
| `POST` | `/api/twin/objective/validate` | Validate scoring expression |
| `POST` | `/api/twin/hook/test` | Test simulation hook script |
| `GET` | `/api/twin/{schema_id}/training-data` | All GP training points |

### Knowledge Graph
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/graph/stats` | Graph node/edge counts |
| `GET` | `/api/graph/materials` | All material nodes |
| `GET` | `/api/graph/connections/{name}` | Connections for a material |
| `GET` | `/api/materials/search` | Graph-enhanced semantic search |

### Chat
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Send message (RAG + optional web search) |
| `GET` | `/api/chat/sessions` | List sessions |
| `GET` | `/api/chat/sessions/{id}/history` | Get session message history |
| `DELETE` | `/api/chat/sessions/{id}` | Clear session |

### Compliance
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/compliance` | List all compliance personas |
| `POST` | `/api/compliance` | Add custom persona |
| `DELETE` | `/api/compliance/{key}` | Delete custom persona |

### Settings
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/settings` | Get current settings (API key masked) |
| `POST` | `/api/settings` | Update settings (API key, web search toggle) |

### Search & System
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/search` | Semantic search on doc_chunks |
| `GET` | `/health` | Ollama + Qdrant connectivity |
| `GET` | `/api/stats` | Document/experiment/chunk counts |

---

## 14. Project Phases

### Phase 1 — Core Ingestion Pipeline ✅ Complete
PDF upload → LLM extraction → Qdrant storage → job queue with priority tiers.

### Phase 2 — Research Loop & Experiments ✅ Complete
Autonomous loop orchestrator, experiment CRUD, knowledge graph, composite scoring, HITL approval gate.

### Phase 3 — Chat & Knowledge Inspection ✅ Complete
RAG chat with 3 roles, SSE streaming, session memory in Qdrant, DocumentDetails modal with 6 tabs.

### Phase 4 — Bug Fixes & Data Quality ✅ Complete
Folder upload multi-file fix, chat blank screen fix, re-extract UI fixes, bulk delete, research field extraction.

### Phase 5 — UI/UX Overhaul ✅ Complete
Electric Indigo glassmorphism design system, collapsible sidebar, Kanban board, page transitions, stat card redesign.

### Phase 6 — Chat Enhancement ✅ Complete
- [x] Tavily web search integration (`web_search.py`, `web_crawler.py`)
- [x] Query rephrasing before retrieval (pronoun resolution)
- [x] `<thinking>` tag stripping
- [x] Memory window: 10 turns / 3000-char soft budget
- [x] Document Parser role
- [x] Source citations (filename + score + chunk preview)
- [x] Compliance Auditor role + dynamic personas (`compliance_personas.py`)
- [x] Settings store + SettingsPanel UI (`settings_store.py`)

### Phase 7 — GP Surrogate & Digital Twin 🔲 Partially Complete

Core GP and BO infrastructure is built and working. Simulation integration and fine-tuning dataset pipeline are **not yet finalised** and are active work items.

**Done:**
- [x] `ExperimentSchema` — parameters, properties, constraints (`surrogate/schema.py`)
- [x] BoTorch GP surrogate model (`surrogate/model.py`)
- [x] Surrogate registry with disk persistence (`surrogate/registry.py`)
- [x] Latin Hypercube DoE for cold start (`surrogate/doe.py`)
- [x] EI acquisition function (`surrogate/acquisition.py`)
- [x] Literature seeding from indexed papers (`surrogate/literature_seed.py`)
- [x] BO-aware autonomous loop (`orchestrator.py` BO mode, `surrogate/loop.py`)
- [x] Digital twin — interactive predict, virtual runs, space maps (`twin.py`, `twin_routes.py`)
- [x] Custom SymPy scoring expressions (`custom_objective.py`)
- [x] Simulation hook runner scaffold (`sim_hook.py`)
- [x] SchemaBuilder UI (`SchemaBuilder.jsx`)
- [x] Two-tier LRU/TTL cache (`cache.py`)

**Not yet finalised:**
- [ ] **Materials simulation pipeline** — the simulation hook (`sim_hook.py`) exists as a subprocess bridge but the actual simulation workflows (FEA, molecular dynamics, or empirical models for specific material classes) are not yet defined. Need to decide: which simulation tools to integrate, what property outputs they produce, and how to map them to the GP property space
- [ ] **Simulation result ingestion** — automated parsing of simulation output files back into the training set
- [ ] **Validation of GP predictions against real experimental data** — the surrogate needs to be benchmarked against actual lab measurements before being used to drive real experimental decisions

**Fine-tuning dataset pipeline (active priority):**
- [ ] **Convert parsed documents into LLM fine-tuning dataset** — design a pipeline that takes the structured extraction results (material names, properties, key findings, methodology) already stored in Qdrant and generates Q&A / instruction-response pairs suitable for fine-tuning a base model on materials science domain knowledge. Decisions needed: output format (JSONL Alpaca / ShareGPT / custom), question generation strategy (property lookup, comparison, reasoning), quality filtering by extraction confidence, and de-duplication across overlapping document chunks

### Phase 8 — LLM Fine-Tuning 🔲 Active Priority

**This is the current focus of development.**

The goal is to fine-tune a base LLM on Planet Material Labs' internal corpus so it has deep domain knowledge of the specific materials, properties, and formulations in the knowledge base — reducing hallucination and improving extraction accuracy on proprietary material classes.

- [ ] **Fine-tuning dataset generation pipeline** — convert Qdrant-stored extraction results into structured training samples
  - Property lookup pairs: `"What is the tensile strength of [material]?"` → `"[value] [unit] (source: [filename])"`
  - Comparison pairs: `"Compare [material A] and [material B] on elongation"` → structured comparison from stored properties
  - Reasoning pairs from key findings and methodology fields
  - Quality filtering: only samples from docs with `extraction_confidence > 0.7`
  - De-duplication across overlapping chunks from the same document
  - Output format: JSONL in Alpaca (`instruction` / `input` / `output`) or ShareGPT (`conversations`) format — decision pending
- [ ] **Data volume assessment** — determine how many fine-tuning samples the current corpus produces and whether it's sufficient
- [ ] **Base model selection** — evaluate `qwen2.5:3b` vs `qwen2.5:7b` as fine-tuning targets; smaller model fine-tuned on domain data may outperform larger general model for extraction tasks
- [ ] **Fine-tuning infrastructure** — LoRA/QLoRA setup (likely via `unsloth` or `llama-factory`) on the RTX 3050 (4GB VRAM constraint is significant)
- [ ] **Evaluation** — extraction accuracy before/after fine-tuning on a held-out set of documents
- [ ] **Model integration** — replace Ollama-pulled base model with the fine-tuned GGUF in `config.yaml`

### Phase 9 — Multi-Model Routing & Settings 🔲 Pending
- [x] Per-task model routing implemented: `CHAT_MODEL`, `ORCHESTRATOR_MODEL`, `LLM_MODEL` correctly used
- [ ] Hot-swap model selection in SettingsPanel UI (currently requires `config.yaml` edit + restart)
- [ ] `config.reload_config()` wired to a Settings API endpoint
- [ ] Model health check per task in the UI

---

## 15. Setup & Running

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Backend runtime |
| Node.js 18+ | Frontend build |
| Ollama | Download from ollama.com; CUDA drivers recommended |
| Qdrant | Run locally on port 6333, or use embedded local storage |
| NVIDIA GPU | Optional but strongly recommended |

### 1. Start Qdrant

```bash
# Docker (recommended)
docker run -p 6333:6333 -v ./qdrant_storage:/qdrant/storage qdrant/qdrant

# Or run the Qdrant binary directly
qdrant.exe
```

If Qdrant is unavailable, the backend automatically falls back to local embedded Qdrant stored at `backend/data/qdrant_storage/`.

### 2. Pull Ollama models

```bash
ollama pull qwen2.5:3b-instruct-q4_K_S    # extraction
ollama pull qwen2.5:7b-instruct-q4_K_S    # chat
ollama pull qwen2.5:3b-instruct-q4_K_M    # orchestrator
ollama pull nomic-embed-text               # embeddings
```

### 3. Configure (optional)

Edit `config.yaml` in the project root to change models, ports, chunk sizes, or any tuning parameters. All backend modules read from this file.

### 4. Start the backend

```bash
cd backend
pip install -r requirements.txt
python main.py
# Listening on http://localhost:8000
```

### 5. Start the frontend

```bash
# Project root
npm install
npm run dev
# Opens http://localhost:5173
```

### First-time Qdrant initialisation

If Qdrant is freshly installed:
```bash
cd backend
python startup.py
```

### Enabling web search

1. Get a Tavily API key from [tavily.com](https://tavily.com)
2. Open the SettingsPanel in the UI, paste the key, toggle web search on
3. Or set `TAVILY_API_KEY` in `config.yaml` under `chat.web_search.api_key`

### Dev reset (clean slate)

```bash
cd backend
python refresh_system.py
```
This stops the backend, wipes all Qdrant collections, and clears uploads.

---

## 16. Directory Structure

```
rlresearchassistant/
├── config.yaml               # Single source of truth for all configuration
├── backend/
│   ├── main.py               # FastAPI app + all API routes
│   ├── twin_routes.py        # Digital twin API router (/api/twin/*)
│   ├── config.py             # Config loader (reads config.yaml)
│   ├── parser.py             # PDF → raw text
│   ├── extractor.py          # LLM property extraction
│   ├── llm.py                # Ollama client (connection pooling)
│   ├── qdrant_store.py       # Storage layer (9 collections)
│   ├── qdrant_mgr.py         # Higher-level search wrapper
│   ├── job_queue.py          # Priority queue + background worker
│   ├── orchestrator.py       # Autonomous loop state machine
│   ├── experiment_runner.py  # Prediction + composite scoring
│   ├── knowledge_graph.py    # NetworkX graph + PageRank re-ranking
│   ├── chat.py               # RAG chat engine (5 roles, 10-turn memory)
│   ├── compliance_personas.py # Compliance auditor role definitions
│   ├── settings_store.py     # Runtime settings (API keys, flags)
│   ├── web_search.py         # Tavily search
│   ├── web_crawler.py        # HTML scraper for web results
│   ├── cache.py              # Two-tier LRU/TTL cache
│   ├── crawler.py            # Recursive folder scanner
│   ├── bulk_parser.py        # LangChain batch folder ingestion
│   ├── twin.py               # Digital twin functions
│   ├── custom_objective.py   # SymPy safe expression evaluator
│   ├── sim_hook.py           # External simulation hook runner
│   ├── startup.py            # One-time Qdrant collection init
│   ├── refresh_system.py     # Dev reset utility
│   ├── requirements.txt
│   ├── surrogate/
│   │   ├── __init__.py
│   │   ├── schema.py         # ExperimentSchema definition
│   │   ├── encoder.py        # Parameter normalisation
│   │   ├── model.py          # BoTorch SingleTaskGP wrapper
│   │   ├── registry.py       # GP model cache + persistence
│   │   ├── doe.py            # Latin Hypercube sampling
│   │   ├── acquisition.py    # Expected Improvement
│   │   ├── loop.py           # BO iteration + approval recording
│   │   └── literature_seed.py # GP warm-start from literature
│   └── data/
│       ├── uploads/          # Temp upload staging
│       ├── parsed/           # Cached extracted JSON
│       ├── surrogates/       # Persisted GP model checkpoints
│       ├── .cache/           # Two-tier cache (embeddings, LLM, pagerank)
│       └── qdrant_storage/   # Embedded Qdrant on-disk storage
│
├── src/
│   ├── App.jsx
│   ├── index.css             # Full design system (tokens, components, animations)
│   └── components/
│       ├── Sidebar.jsx
│       ├── GoalPanel.jsx
│       ├── KnowledgePanel.jsx
│       ├── ExperimentDashboard.jsx
│       ├── ExperimentsPanel.jsx
│       ├── ResultsPanel.jsx
│       ├── DecisionPanel.jsx
│       ├── PapersView.jsx
│       ├── DocumentDetails.jsx
│       ├── SchemaBuilder.jsx     # Experiment schema designer (Phase 7)
│       ├── SettingsPanel.jsx     # Runtime settings UI (Phase 6)
│       ├── ChatPanel.jsx
│       └── CyberLoader.jsx
│
├── tests/                    # Backend unit tests
├── public/
├── dist/                     # Vite production build output
├── vite.config.js
├── package.json
└── README.md
```

---

## 17. Known Limitations & Design Decisions

### Single background worker
One worker thread processes one document at a time — intentional, since the RTX 3050 has 4GB VRAM and two concurrent LLM jobs would cause OOM errors.

### Scanned-only PDFs
No OCR. Image-only PDFs return empty text. Documents are indexed as a manifest with zero properties and a warning is logged.

### KnowledgePanel uses mock data
`KnowledgePanel.jsx` renders hardcoded demo content rather than fetching from the live `/api/graph/materials` endpoint. Wiring this to real data is a known pending item.

### Chat session identity
Session IDs live in React component state. Refreshing the browser generates a new UUID — the old session is still in Qdrant but not automatically re-attached. Persisting to `localStorage` is a pending improvement.

### Knowledge graph rebuild latency
Graph is rebuilt from Qdrant every 300s. Heavy ingestion during a session means the graph may lag by up to 5 minutes. Configurable via `knowledge_graph.cache_ttl` in `config.yaml`.

### GP surrogate warm-up
With fewer than 3 approved experiments, the system falls back to Latin Hypercube DoE sampling. Property predictions in early iterations are based on literature seeding only and should be treated as initial suggestions, not accurate forecasts.

### No authentication layer
Designed for single-user, local-only deployment. Do not expose port 8000 to a wider network without adding an auth layer.

### No desktop packaging yet
The app runs as a browser-based Vite dev server. There is no desktop wrapper — Tauri has been removed from the project. Packaging strategy (if needed) is not yet decided.

### LLM extraction non-determinism
Temperature is set to 0.0 for extraction, but GGUF runtime introduces minor sampling variance at low temperatures. Confidence scores are approximate indicators.

### `config.reload_config()` not yet wired
The hot-reload function exists in `config.py` but no API endpoint calls it. Model changes in `config.yaml` currently require a backend restart.
