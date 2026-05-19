# Session Notes — RLResearchAssistant Ideation

**Date:** 2026-05-17

---

## 1. Current System Status

Planet Material Labs — AI Research Assistant for accelerated materials science research. Runs 100% offline on local hardware (Windows 11, RTX 3050 4GB, 16GB RAM).

**Stack:**
- Frontend: React 18, Vite, TypeScript, Recharts, lucide-react
- Desktop: Tauri 2.x (scaffolded)
- Backend: FastAPI, Python 3.11+, Uvicorn
- LLM: Ollama (qwen2.5:3b/14b), nomic-embed-text
- Vector DB: Qdrant (8 collections)
- Surrogate: BoTorch (SingleTaskGP per property)
- PDF: pdfplumber + PyPDF2
- KG: NetworkX
- Optimization: SymPy, BoTorch

---

## 2. Project Phases Status

| Phase | Description | Status |
|---|---|---|
| 1 | Core Ingestion Pipeline (PDF→LLM→Qdrant) | ✅ Complete |
| 2 | Research Loop & Experiments | ✅ Complete |
| 3 | Chat & Knowledge Inspection (RAG) | ✅ Complete |
| 4 | Bug Fixes & Data Quality | ✅ Complete |
| 5 | UI/UX Overhaul (Electric Indigo glassmorphism) | ✅ Complete |
| 6 | Chat Enhancement (web search, query rephrasing, more roles) | 🔲 Pending |
| 7 | Orchestrator Intelligence (iteration memory, auto result ingest, literature seed, Digital Twin, RL) | 🔲 Pending |
| 8 | Multi-Model Routing (right model per task) | 🔲 Pending |
| 9 | Desktop Application (Tauri packaging, bundled Qdrant/Ollama) | 🔲 Pending |

---

## 3. Experimentation Tab — Implementation Status

### What Works (Real, Qdrant-backed)
- List/create/delete experiments
- GP surrogate predictions (BoTorch)
- Composite scoring (schema-driven: weights, targets, directions)
- Kanban board (Queued / Running / Completed) in UI
- Loop iterations auto-saved as experiments

### What's Mock / Placeholder
- `PUT /api/experiments/{id}` — returns success, no persist
- `POST /api/experiments/{id}/results` — returns success, no persist
- Manual experiment creation from UI — no candidate generation

### Known Bugs/Gaps
- LLM vocabulary tuned for general polymers (misses EMI shielding, thermal conductivity, Tg, dielectric constant)
- Scanned PDFs — no OCR, returns empty
- Context truncation at ~8000 chars
- Cost dimension hardcoded at 0.7 across all materials
- Loop fallback logic — hardcoded configs (Polycarbonate, EPDM, Nylon 66) when LLM fails

---

## 4. BoTorch GP Surrogate (Scientifically Real)

### Architecture

```
schema.properties
  ├── PropertyGP("Tensile Strength") → SingleTaskGP(X, y)
  ├── PropertyGP("Elongation")       → SingleTaskGP(X, y)
  └── PropertyGP("Modulus")          → SingleTaskGP(X, y)

SurrogateModel wraps all PropertyGPs into unified predict(X)/fit(X,Y)
```

### How It Works
1. **No data** → Latin Hypercube DoE (initial exploration designs)
2. **≥3 training points** → BoTorch SingleTaskGP trains on (X, y)
3. **New candidates** → Acquisition function (EI/UCB) picks highest utility
4. **Scientist approves** → Observation added → GP retrains
5. **Repeat** → GP uncertainty shrinks, predictions get more accurate

### Persistence
- Models saved to disk at `SURROGATE_DIR/{schema_id}/{property_name}.pt`
- Loaded on demand via registry (lazy loading)

### Literature Seeding (`literature_seed.py`)
- Queries Qdrant `material_properties` collection
- Extracts numeric values with unit normalization (MPa, GPa, °C, %)
- Generates synthetic compositions via Latin Hypercube sampling
- Seeds GP with up to 50 points per property

---

## 5. Digital Twin (`twin.py` + `sim_hook.py`)

### Current Capabilities
- `interactive_predict()` — instant multi-property GP prediction for any formulation
- `virtual_run()` — run N BO iterations with GP as "lab oracle" (mean predictions become "observed" ground truth)
- `space_map()` — 2D grid heatmap over any two parameter dimensions
- `sim_hook.py` — external script execution (subprocess), blend GP + simulation predictions

### Enhancement Considerations
- **Physics-based simulation** — LAMMPS, MD packages, FEA, thermodynamic calculators
- **Domain-specific models** — MatBERT, GNNs for molecular structure
- **Ensemble (GP + NN + physics residual)** — combine uncertainty (GP) with accuracy (NN)
- **Real-time what-if** — JIT compiled inference, WebSocket streaming predictions, LRU caching
- **Physics residual learning** — GP learns the residual (difference) between physics simulation and real measurements

---

## 6. RL Agent Integration

## Concept
```
Goal → RL Agent (acts in Digital Twin/GP environment) →
Many virtual experiments → Policy learns best sequence →
RL returns top-K candidates ranked by learned policy →
Scientist reviews → Approve → Real lab validation
```

### MDP Definition
| Component | Definition |
|---|---|
| **State** | (current best composition, goal weights, iteration count, GP model state) |
| **Action** | Next composition to try |
| **Reward** | Composite score improvement over prior iterations |
| **Trajectory** | Full experiment history per goal |

### Implementation Options
| Option | Complexity | Description |
|---|---|---|
| **Offline RL (BCO)** | Medium | Behavior Clone from history, train on existing experiment data |
| **Online RL in Twin** | High | Train in Digital Twin, deploy best policy |
| **Ensemble (RL + EI)** | Low | Use RL when data-rich, EI when data-sparse |

### Cross-Goal Generalization
- Policy trained on multiple goals generalizes to new goals
- Avoids retraining from scratch each time

### Value
- Learned policy > hand-tuned EI
- High-throughput virtual screening inside Digital Twin
- Active research area: "Bayesian Optimization with RL"

---

## 7. AutoML for Surrogate Selection

Use AutoML to automatically select best surrogate model per property.

### Concept
- Try multiple models: GP (BoTorch), Random Forest, XGBoost, Neural Network
- Auto-select based on cross-validation score
- Re-train on new observations

### Model Registry
```python
MODELS = {
    "gp": lambda: BoTorchGP(),
    "rf": lambda: RandomForestRegressor(),
    "xgb": lambda: XGBRegressor(),
    "nn": lambda: MLPRegressor(),
}
```

### Integration Points
- Replace hardcoded GP selection with AutoML
- Blend predictions via ensemble weighting
- Hyperparameter tuning (grid search)
- Integrate into surrogate registry

---

## 8. Phase 7 — Work Items

### P0: Quick Wins
| # | Item | Description | File Changes |
|---|---|---|---|
| 1 | **Iteration Memory** | Feed last 5 iterations to LLM context | `orchestrator.py`, `experiment_runner.py` |
| 2 | **Auto Result PDF Ingestion** | Detect result PDFs, auto-parse measurements, feed back to experiments | `parser.py`, `extractor.py`, `qdrant_store.py`, `main.py` |
| 3 | **Literature Seeding** | Verify and wire `seed_from_literature()` on startup | `surrogate/registry.py`, `main.py` |

### P1: Digital Twin Enhancement
| # | Item | Description |
|---|---|---|
| 1 | Physics sim hooks | Standardized interface for LAMMPS/MD/FEA |
| 2 | Real-time what-if | JIT, WebSocket streaming, LRU cache |
| 3 | Batch prediction | Multi-composition endpoint |

### P2: RL + AutoML
| # | Item | Description |
|---|---|---|
| 1 | RL agent | Offline/online RL for experiment policy |
| 2 | AutoML | Auto-select best surrogate model per property |
| 3 | RL + Twin integration | Virtual high-throughput screening |

### New API Endpoints
| Method | Path |
|---|---|
| POST | `/api/experiments/{exp_id}/results` |
| PUT | `/api/experiments/{exp_id}` |
| POST | `/api/twin/{schema_id}/batch-predict` |
| POST | `/api/twin/{schema_id}/virtual-run` |
| POST | `/api/surrogate/{schema_id}/autoselect` |
| POST | `/api/rl/{schema_id}/train` |
| POST | `/api/rl/{schema_id}/suggest` |

---

## 9. Files to Create

```
backend/hooks/                  # Physics simulation templates
backend/hooks/__init__.py
backend/hooks/lammps_md.py      # MD simulation template
backend/rl/                     # RL agent implementation
backend/rl/agent.py             # RL policy class
backend/rl/trainer.py           # Offline RL trainer
backend/automl/                 # AutoML surrogate selection
backend/automl/selector.py      # Auto-select model
```

---

## 10. Open Questions & Further Ideation

### On the Loop
- Should RL replace BO entirely or complement it (ensemble)?
- Should the loop have a "plan horizon" (look ahead N steps)?
- Multi-fidelity: cheap GP evaluations vs expensive real experiments?

### On Physics
- Which physics simulators should be supported first? (Molecular dynamics → DFT → FEA?)
- Should physics be a pre-filter or a post-processor?
- Unit conversion library needed for physics inputs?

### On AutoML
- How often should AutoML re-evaluate model selection?
- Should AutoML run per-property or globally?
- Model size constraints on RTX 3050 (4GB VRAM)?

### On UI/UX
- Should the Digital Twin have its own tab in the sidebar?
- RL training progress bar in UI?
- "Simulation" vs "Real" data markers in results charts?

### On Data
- Data format for physics simulation inputs/outputs?
- How to store/manage physics simulation results (separate Qdrant collection?)
- Experiment result PDF format detection — how to ensure correct parsing?

### Architecture Scaling
- As we add more model types (GP, RF, XGB, NN, RL), how should the architecture scale?
- Could a plugin system help for physics simulators?
- Should the backend support multi-worker for parallel sim evaluation?
