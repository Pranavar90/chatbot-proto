# Phase 7 — Implementation Plan

## Overview

This phase delivers three major capability blocks:

| Block | Description | Priority |
|---|---|---|
| **Orchestrator Intelligence** | Iteration memory, auto result PDF ingestion, literature seeding | P0 |
| **Digital Twin Enhancement** | Physics-based simulation, domain models, real-time what-if | P1 |
| **RL Integration** | RL agent inside Digital Twin for high-throughput virtual screening | P2 |

---

## P0: Orchestrator Intelligence (Quick Wins)

### 0.1 — Iteration Memory

**Problem:** LLM only sees current iteration. No history available.

**Current state:** LLM prompt in `orchestrator.py` lines 249-331 only receives:
```
RESEARCH GOAL: {goal}
CURRENT HYPOTHESIS: {hypothesis}
ITERATION: {iteration}
RETRIEVED KNOWLEDGE: {context}
```

**Solution:** Feed full loop history to LLM context.

**Implementation:**

1. **Store history** — `orchestrator.py` maintains `loopState.history[]` (list of iteration objects)

2. **Format as context** — Create helper in `orchestrator.py`:
   ```python
   def _format_iteration_history(history: List[Dict]) -> str:
       if not history:
           return "(No previous iterations)"
       lines = ["## Previous Iterations:"]
       for h in history[-5:]:  # Last 5 iterations
           lines.append(f"- Iteration {h.get('iteration')}:")
           lines.append(f"  Composition: {h.get('composition')}")
           lines.append(f"  Predicted: {h.get('predictions')}")
           lines.append(f"  Score: {h.get('score')}")
           lines.append(f"  Status: {h.get('outcome', 'pending')}")
       return "\n".join(lines)
   ```

3. **Inject in `_generate_candidates()`** — Append formatted history to prompt context

4. **Add to `experiment_runner.py`** — Include history in `predict_properties()` context so predictions are grounded in prior learnings

---

### 0.2 — Auto Result PDF Ingestion

**Problem:** Manual "Add Result" step after lab testing.

**Current state:**
- `POST /api/experiments/{exp_id}/results` exists but is a mock
- No auto-detection of result PDFs from crawler

**Solution:** Detect experiment result PDFs and auto-feed measurements back to experiments.

**Implementation:**

1. **Add result detection in `parser.py`** — New document type "result":
   ```python
   RESULT_INDICATORS = [
       "test results", "measurement results", "experiment results",
       "test report", "measurement report", "data report",
       "test conditions:", "sample id", "batch no", "lot number",
       "test date", "operator:", "equipment:", "test standard",
   ]
   ```

2. **New extraction prompt in `extractor.py`** — `SYSTEM_PROMPT_RESULT`:
   ```python
   Extract from measurement test reports:
   {
     "material": str,
     "test_date": str,
     "conditions": {param: value},
     "results": [{"property": str, "value": float, "unit": str, "passed": bool}],
     "experiment_id": str  (if detectable)
   }
   ```

3. **Auto-match logic in `crawler.py` or `job_queue.py`:**
   - If document type == "result", check for linked experiment
   - If found, upsert measurements to `experiments` collection
   - If not found, store in `results` collection for later linking

4. **Wire up `/api/experiments/{exp_id}/results`** — Replace mock with real implementation in `main.py`:
   ```python
   @app.post("/api/experiments/{exp_id}/results")
   async def add_experiment_results(exp_id: str, results: ResultsRequest):
       # Upsert to Qdrant experiments collection
       store.upsert_experiment_results(exp_id, results.results)
   ```

5. **Add `upsert_experiment_results()` to `qdrant_store.py`**

---

### 0.3 — Literature Seeding

**Problem:** `literature_seed.py` exists but may not be wired on startup.

**Current state:** Function `seed_from_literature(schema)` exists, used during GP training but may not trigger automatically.

**Solution:** Verify and enhance wiring.

**Implementation:**

1. **Ensure `seed_from_literature()` runs on GP training:**
   - In `surrogate/registry.py` — call during `get_or_load()` if no persisted data

2. **Add startup trigger in `main.py`:**
   ```python
   @app.on_event("startup")
   async def seed_surrogates_on_startup():
       store = get_store()
       for schema in store.list_schemas():
           registry.seed_from_schema(schema.schema_id)
   ```

3. **Verify unit normalization** — Ensure `literature_seed.py` handles common materials science units (MPa, GPa, °C, %)

4. **Cap max seeding points** — Default 50 points per property to avoid slow startup

---

## P1: Digital Twin Enhancement

### 1.1 — Physics-Based Simulation Hooks

**Problem:** GP is statistical, not physics-informed.

**Current state:** `sim_hook.py` supports external script execution, already called by `twin.py`.

**Solution:** Extend hook architecture for physics simulators.

**Implementation:**

1. **Standardize hook interface:**
   ```python
   class PhysicsHook:
       def __init__(self, script_path: str, schema: ExperimentSchema):
           self.script = script_path
           self.schema = schema

       def predict(self, composition: dict) -> dict:
           # Returns {property: {"mean": float, "unit": str}}
   ```

2. **Pre-built hook templates:**
   - `hooks/lammps_md.py` — Molecular dynamics template
   - `hooks/thermo_calc.py` — Thermodynamic calculation template
   - `hooks/fea.py` — Finite element analysis template

3. **GP + Physics blending:**
   - Physics prediction replaces GP mean for overlapping properties
   - GP std retained as uncertainty
   - Blended via existing `sim_hook.blend_predictions()`

4. **Schema-aware hooks:**
   - Pass schema metadata (property names, units) to hook
   - Validate hook output against expected properties

---

### 1.2 — Real-Time What-If Analysis

**Problem:** Current what-if requires API calls.

**Solution:** Accelerate interactive predictions.

**Implementation:**

1. **JIT compilation:**
   - Cache encoded compositions
   - Use `torch.jit.script` for model inference

2. **Batch prediction endpoint:**
   ```python
   @app.post("/api/twin/{schema_id}/batch-predict")
   async def batch_predict(schema_id: str, compositions: List[dict]):
       # Return predictions for N compositions in one call
   ```

3. **WebSocket for streaming updates:**
   ```python
   @app.websocket("/ws/twin/{schema_id}/predict")
   async def ws_predict(websocket, schema_id, composition):
       # Stream predictions as composition changes via slider
   ```

4. **Caching layer:**
   - LRU cache for composition → prediction
   - Cache invalidation on GP retrain

---

## P2: RL Integration

### 2.1 — RL Agent Design

**Problem:** Hand-tuned acquisition (EI, UCB) may not be optimal for all goals.

**Solution:** Train RL policy to learn experiment sequencing.

**Concept:**
```
Goal → RL Agent (acts in Digital Twin/GP environment) →
Many virtual experiments → Policy learns best sequence →
RL returns top-K candidates ranked by learned policy →
Scientist reviews → Approve → Real lab validation
```

**MDP Definition:**

| Component | Definition |
|---|---|
| **State** | (current best composition, goal weights, iteration count, GP model state) |
| **Action** | Next composition to try |
| **Reward** | Composite score improvement over prior iterations |
| **Trajectory** | Full experiment history per goal |

**Implementation Options:**

| Option | Complexity | Description |
|---|---|---|
| **Offline RL (BCO)** | Medium | Behavior Clone from history, train on existing experiment data |
| **Online RL in Twin** | High | Train in Digital Twin, deploy best policy |
| ** Ensemble (RL + EI)** | Low | Use RL when data-rich, EI when data-sparse |

---

### 2.2 — AutoML for Surrogate Selection

**Added:** Use AutoML to automatically select best surrogate model per property.

**Concept:**
- Try multiple models: GP (BoTorch), Random Forest, XGBoost, Neural Network
- Auto-select based on cross-validation score
- Re-train on new observations

**Implementation:**

1. **Model registry:**
   ```python
   class AutoSurrogate:
       MODELS = {
           "gp": lambda: BoTorchGP(),
           "rf": lambda: RandomForestRegressor(),
           "xgb": lambda: XGBRegressor(),
           "nn": lambda: MLPRegressor(),
       }

       def fit_autoselect(self, X, y, cv=5):
           # Try all models, select best by CV score
   ```

2. **Blend predictions:**
   - Use ensemble weighted by model confidence
   - Uncertainty from GP, mean from weighted blend

3. **Hyperparameter tuning:**
   - Basic grid search on model params
   - Integrate into `surrogate/registry.py`

---

### 2.3 — RL + Digital Twin Integration

**Implementation:**

1. **Virtual high-throughput screening:**
   ```python
   def rl_virtual_screening(schema_id, goal, n_iterations=100):
       # Run RL in Digital Twin (GP as environment)
       # Return top-K candidates with uncertainty
   ```

2. **Policy persistence:**
   ```python
   @app.post("/api/rl/{schema_id}/train")
   async def train_rl_policy(schema_id):
       # Train on experiment history
       # Save policy to disk
   ```

3. **Crossover with BO:**
   - If RL policy not trained → fallback to BO/DoE
   - If RL policy trained → use for candidate selection
   - Ensemble both scores in UI

---

## API Endpoints to Add

| Method | Path | Description |
|---|---|---|
| POST | `/api/experiments/{exp_id}/results` | Real measurement upsert |
| PUT | `/api/experiments/{exp_id}` | Real experiment update |
| POST | `/api/twin/{schema_id}/batch-predict` | Batch predictions |
| POST | `/api/twin/{schema_id}/virtual-run` | Virtual BO run |
| POST | `/api/surrogate/{schema_id}/autoselect` | AutoML surrogate selection |
| POST | `/api/rl/{schema_id}/train` | Train RL policy |
| POST | `/api/rl/{schema_id}/suggest` | RL candidate suggestion |

---

## Files to Modify

| File | Changes |
|---|---|
| `orchestrator.py` | Add iteration history formatting |
| `experiment_runner.py` | Include history in context |
| `parser.py` | Add result document detection |
| `extractor.py` | Add result extraction prompt |
| `crawler.py` / `job_queue.py` | Auto-link result to experiment |
| `qdrant_store.py` | Add upsert_experiment_results |
| `main.py` | Wire up real /results and /update endpoints |
| `surrogate/registry.py` | Seed on startup |
| `twin.py` | Physics hook enhancement |
| `sim_hook.py` | Standardize hook interface |
| `hooks/` (new) | Physics simulation templates |

---

## Files to Create

| File | Description |
|---|---|
| `backend/hooks/` | Physics simulation templates directory |
| `backend/hooks/__init__.py` | Hook loader |
| `backend/hooks/lammps_md.py` | MD simulation template |
| `backend/rl/` | RL agent implementation |
| `backend/rl/agent.py` | RL policy class |
| `backend/rl/trainer.py` | Offline RL trainer |
| `backend/automl/` | AutoML surrogate selection |
| `backend/automl/selector.py` | Auto-select model |

---

## Testing Strategy

| Component | Test |
|---|---|
| Iteration Memory | Generate candidates with full history; verify last 5 iterations appear in prompt |
| Auto Result Ingest | Upload result PDF; verify measurements appear in experiment |
| Literature Seed | Check GP training uses literature data (n_points > 0 after seed) |
| Physics Hook | Run with mock sim; verify GP + physics blend |
| Digital Twin | Slider drag → prediction updates < 100ms |
| AutoML | Run autoselect; verify chosen model in status endpoint |
| RL Integration | Train on history; verify policy scores candidates |

---

## Success Criteria

- [ ] Iteration history appears in LLM context (last 5 iterations minimum)
- [ ] Result PDFs auto-detected and linked to experiments
- [ ] Literature seeding runs on startup, adds points to GP
- [ ] Physics hooks execute and blend with GP predictions
- [ ] Batch/streaming predictions < 100ms latency
- [ ] AutoML selects model per property
- [ ] RL policy generates candidates in Digital Twin