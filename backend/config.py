"""
config.py — Central configuration loaded from config.yaml.

All values are read from the YAML file at startup.
Changing config.yaml and restarting the backend applies all changes.

Backward compatibility: every constant from the old config.py is still available
as a module-level variable so no other file needs to change.
"""

import os
import threading
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR.parent / "config.yaml"


def _load_yaml() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_cfg = _load_yaml()

# ── Helper: nested dict access ────────────────────────────────────────────────

def _get(path: str, default=None):
    """Dot-path access into the YAML config, e.g. _get('llm.models.extraction')."""
    keys = path.split(".")
    val = _cfg
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return default
    return val


# ── Server ────────────────────────────────────────────────────────────────────

API_PORT = _get("server.api_port", 8000)
API_HOST = _get("server.host", "0.0.0.0")
CORS_ORIGINS = _get("server.cors_origins", ["http://localhost:5173"])

# ── Paths ─────────────────────────────────────────────────────────────────────

DATA_DIR = BASE_DIR / _get("paths.data_dir", "data")
PARSED_DIR = BASE_DIR / _get("paths.parsed_dir", "data/parsed")
QDRANT_DIR = BASE_DIR / _get("paths.qdrant_storage", "data/qdrant_storage")
UPLOADS_DIR = BASE_DIR / _get("paths.uploads_dir", "data/uploads")
SURROGATE_DIR = BASE_DIR / _get("paths.surrogates_dir", "data/surrogates")
CACHE_DIR = BASE_DIR / _get("paths.cache_dir", "data/.cache")

DATA_DIR.mkdir(parents=True, exist_ok=True)
PARSED_DIR.mkdir(parents=True, exist_ok=True)
QDRANT_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
SURROGATE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Ollama / LLM ─────────────────────────────────────────────────────────────

OLLAMA_BASE = _get("llm.base_url", "http://localhost:11434")
LLM_MODEL = _get("llm.models.extraction", "qwen2.5:3b-instruct-q4_K_S")
CHAT_MODEL = _get("llm.models.chat", LLM_MODEL)
ORCHESTRATOR_MODEL = _get("llm.models.orchestrator", LLM_MODEL)
EMBED_MODEL = _get("llm.models.embedding", "nomic-embed-text")
AVAILABLE_MODELS = _get("llm.available_models", [
    "phi3:mini",
    "qwen2.5:3b-instruct-q4_K_S",
    "qwen2.5:7b-instruct-q4_K_S",
    "qwen2.5:14b-instruct-q4_K_S",
    "llama3.2:3b",
    "gemma3:4b",
])

# GPU options
NUM_GPU = _get("llm.gpu.num_gpu", 99)
NUM_CTX = _get("llm.gpu.num_ctx", 8192)
KEEP_ALIVE = _get("llm.gpu.keep_alive", "15m")
EMBED_GPU_LAYERS = _get("embedding.gpu_layers", 35)

# Generation defaults
EXTRACTION_TEMPERATURE = _get("llm.generation.extraction_temperature", 0.0)
CHAT_TEMPERATURE = _get("llm.generation.chat_temperature", 0.1)
ORCHESTRATOR_TEMPERATURE = _get("llm.generation.orchestrator_temperature", 0.4)
DECISION_TEMPERATURE = _get("llm.generation.decision_temperature", 0.3)
MAX_RETRIES = _get("llm.generation.max_retries", 1)

# ── Embedding ─────────────────────────────────────────────────────────────────

EMBED_DIM = _get("embedding.dimension", 768)

# ── Document Processing ───────────────────────────────────────────────────────

TDS_EXTRACT_CHARS = _get("documents.extraction.tds_max_chars", 7000)
PAPER_EXTRACT_CHARS = _get("documents.extraction.paper_max_chars", 12000)

CHUNK_SIZE_CHARS = _get("documents.chunking.chunk_size_chars", 2000)
CHUNK_OVERLAP_CHARS = _get("documents.chunking.chunk_overlap_chars", 200)

EXTRACTION_CHUNK_SIZE = _get("documents.extraction_chunking.chunk_size", 4000)
EXTRACTION_CHUNK_OVERLAP = _get("documents.extraction_chunking.chunk_overlap", 300)

TDS_BIAS = _get("documents.doctype.tds_bias", 2)

SUPPORTED_EXTENSIONS = set(_get("documents.supported_extensions", [".pdf", ".docx", ".doc"]))

# ── Qdrant ────────────────────────────────────────────────────────────────────

QDRANT_URL = _get("qdrant.url", "http://localhost:6333")
QDRANT_PATH = str(QDRANT_DIR)
QDRANT_CONNECT_TIMEOUT = _get("qdrant.connect_timeout", 1)

COLL_DOCUMENTS = _get("qdrant.collections.documents", "documents")
COLL_CHUNKS = _get("qdrant.collections.chunks", "doc_chunks")
COLL_PROPERTIES = _get("qdrant.collections.properties", "material_properties")
COLL_EXPERIMENTS = _get("qdrant.collections.experiments", "experiments")
COLL_EDGES = _get("qdrant.collections.edges", "knowledge_edges")
COLL_FOLDERS = _get("qdrant.collections.folders", "scanned_folders")
COLL_JOBS = _get("qdrant.collections.jobs", "job_status")
COLL_CHAT_SESSIONS = _get("qdrant.collections.chat_sessions", "chat_sessions")
COLL_SCHEMAS = _get("qdrant.collections.schemas", "experiment_schemas")
QDRANT_COLLECTION = _get("qdrant.collections.legacy", "parsed_materials")

# ── Knowledge Graph ───────────────────────────────────────────────────────────

GRAPH_CACHE_TTL = _get("knowledge_graph.cache_ttl", 300)
PAGERANK_ALPHA = _get("knowledge_graph.pagerank_alpha", 0.85)
PAGERANK_MAX_ITER = _get("knowledge_graph.pagerank_max_iter", 100)
SEARCH_K = _get("knowledge_graph.search_k", 10)
RERANK_VECTOR = _get("knowledge_graph.rerank.vector_weight", 0.6)
RERANK_PAGERANK = _get("knowledge_graph.rerank.pagerank_weight", 0.3)
RERANK_CONNECTIVITY = _get("knowledge_graph.rerank.connectivity_weight", 0.1)

# ── Job Queue ─────────────────────────────────────────────────────────────────

JOB_PRIORITY_HIGH = _get("job_queue.priority.high_max_bytes", 1048576)
JOB_PRIORITY_MEDIUM = _get("job_queue.priority.medium_max_bytes", 10485760)
JOB_MAX_RETRIES = _get("job_queue.max_retries", 3)

# ── Orchestrator ──────────────────────────────────────────────────────────────

DEFAULT_WEIGHTS = _get("orchestrator.default_weights", {"strength": 0.50, "flexibility": 0.35, "cost": 0.15})
N_CANDIDATES = _get("orchestrator.n_candidates", 3)
BO_N_CANDIDATES = _get("orchestrator.bo_n_candidates", 5)

# ── Chat ──────────────────────────────────────────────────────────────────────

CHAT_MEMORY_TURNS = _get("chat.memory_turns", 4)
CHAT_SEARCH_LIMIT = _get("chat.search_limit", 5)
STRIP_THINKING_TAGS = _get("chat.strip_thinking_tags", True)
WEB_SEARCH_ENABLED = _get("chat.web_search.enabled", False)
WEB_SEARCH_PROVIDER = _get("chat.web_search.provider", "tavily")
TAVILY_API_KEY = _get("chat.web_search.api_key", "")

# ── Surrogate ─────────────────────────────────────────────────────────────────

SURROGATE_LITERATURE_MAX_POINTS = _get("surrogate.literature_seed_max_points", 50)
SURROGATE_MIN_TRAINING_POINTS = _get("surrogate.min_training_points", 3)
SURROGATE_DOE_SAMPLES = _get("surrogate.doe_n_samples", 10)

# ── Qdrant client singleton ──────────────────────────────────────────────────

_qdrant_client = None
_qdrant_lock = threading.Lock()


def get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client
    with _qdrant_lock:
        if _qdrant_client is not None:
            return _qdrant_client
        from qdrant_client import QdrantClient
        try:
            client = QdrantClient(url=QDRANT_URL, timeout=QDRANT_CONNECT_TIMEOUT)
            client.get_collections()
            _qdrant_client = client
            return _qdrant_client
        except Exception:
            _qdrant_client = QdrantClient(path=QDRANT_PATH)
            return _qdrant_client


def reload_config():
    """Hot-reload config.yaml without restarting. Called by Settings API."""
    global _cfg, LLM_MODEL, CHAT_MODEL, ORCHESTRATOR_MODEL, EMBED_MODEL
    global OLLAMA_BASE, NUM_GPU, NUM_CTX, KEEP_ALIVE
    global TDS_EXTRACT_CHARS, PAPER_EXTRACT_CHARS
    global CHUNK_SIZE_CHARS, CHUNK_OVERLAP_CHARS
    global GRAPH_CACHE_TTL, API_PORT

    _cfg = _load_yaml()

    LLM_MODEL = _get("llm.models.extraction", LLM_MODEL)
    CHAT_MODEL = _get("llm.models.chat", CHAT_MODEL)
    ORCHESTRATOR_MODEL = _get("llm.models.orchestrator", ORCHESTRATOR_MODEL)
    EMBED_MODEL = _get("llm.models.embedding", EMBED_MODEL)
    OLLAMA_BASE = _get("llm.base_url", OLLAMA_BASE)
    NUM_GPU = _get("llm.gpu.num_gpu", NUM_GPU)
    NUM_CTX = _get("llm.gpu.num_ctx", NUM_CTX)
    KEEP_ALIVE = _get("llm.gpu.keep_alive", KEEP_ALIVE)
    TDS_EXTRACT_CHARS = _get("documents.extraction.tds_max_chars", TDS_EXTRACT_CHARS)
    PAPER_EXTRACT_CHARS = _get("documents.extraction.paper_max_chars", PAPER_EXTRACT_CHARS)
    CHUNK_SIZE_CHARS = _get("documents.chunking.chunk_size_chars", CHUNK_SIZE_CHARS)
    CHUNK_OVERLAP_CHARS = _get("documents.chunking.chunk_overlap_chars", CHUNK_OVERLAP_CHARS)
    GRAPH_CACHE_TTL = _get("knowledge_graph.cache_ttl", GRAPH_CACHE_TTL)
    API_PORT = _get("server.api_port", API_PORT)
