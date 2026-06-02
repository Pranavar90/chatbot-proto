# PROJECT_PLANNER.md
## Discussion Notes — 2026-05-21

These are notes from planning discussions, not implementation specs.

---

# VLM Integration

- VLM belongs inside the **parser** as a perception/extraction step, NOT in the Q&A pipeline.
- Purpose: extract structured JSON from figures, charts, micrographs embedded in PDFs.
- Output merges with text extraction (pdfplumber etc.) before chunking.
- Candidate models: **Qwen2.5-VL 3B**, **MiniCPM-V 2.6**, **LLaVA 1.6 7B**.
- Model selection needs hands-on testing — no decision made yet.

---

# Temperature & Extraction Settings

- **T=0.0** for all extraction tasks (VLM, text parsing, property extraction).
- **T=0.3** for Q&A generation (slight variation without hallucination).
- Missing paper properties: fix by increasing `PAPER_EXTRACT_CHARS`, not by raising temperature.

---

# Q&A Training Data Pipeline

- Q&A pairs stored in Qdrant under a new **`training_qna`** collection.
- Export format: **JSONL** (not CSV). JSONL is the fine-tuning standard.
- Target dataset size: **2000-5000 pairs** total.

## Four Q&A Categories (with target distribution)
| Category | Share | Description |
|---|---|---|
| Factual lookup | 20-25% | Direct retrieval answers |
| Scientific reasoning | 35-40% | Multi-step inference, causal chains |
| Chain-of-thought | 25-30% | Show-your-work reasoning |
| Negative/refusal | 10-15% | "Not enough info" / out-of-scope |

## Pair Count Scaling
- Not fixed per document. Scales with information density.
- TDS: ~25-60 pairs per document.
- Paper: ~40-90 pairs per document.

---

# Three Generation Tiers

| Tier | Method | Scope |
|---|---|---|
| Tier 1 | Deterministic templates | Single doc, formulaic Q&A (units, properties, definitions) |
| Tier 2 | LLM reasoning per doc | Single doc, requires inference (why/how questions) |
| Tier 3 | Cross-document comparisons | Multi-doc batch, compare materials/methods across papers |

- Tier 3 cross-doc design is **incomplete** — needs further planning.

---

# Model Size Strategy for Scientific Reasoning

- **3B models**: good for extraction + 2-step reasoning chains.
- **7B models**: needed for 3-step+ reasoning chains.
- Strategy: **knowledge distillation** from a frontier model to generate training data.
  - Frontier model generates high-quality CoT pairs.
  - Fine-tuned local model learns to reproduce them.
- Deployment split: **3B for extraction**, **fine-tuned 7B for chat/reasoning**.
- Frontier model choice for CoT distillation: **TBD**.

---

# Fine-Tuning Plan

- Method: **QLoRA** on Kaggle (free GPU).
- Export: **GGUF** format.
- Deployment: load GGUF into **Ollama** for local inference.
- Target: 2000-5000 Q&A pairs before first fine-tune run.

---

# Bedrock / Cloud Compatibility

- Bedrock integration is **Phase 2** — not current priority.
- Plan: abstract an `LLMBackend` interface later to swap local/cloud.
- Current dev environment: **local Ollama + Kaggle** only.

---

# Open Questions

1. **VLM model selection** — Qwen2.5-VL 3B vs MiniCPM-V 2.6 vs LLaVA 1.6 7B. Needs testing on actual TDS/paper figures.
2. **Tier 3 cross-document design** — How to select document pairs/groups, batch strategy, comparison prompt structure.
3. **Frontier model for CoT distillation** — Which model generates the seed chain-of-thought data. No decision.
4. **Negative pair property list** — Which properties/topics should trigger refusal responses. List not defined.
