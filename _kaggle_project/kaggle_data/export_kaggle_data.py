"""
export_kaggle_data.py — Export 100 parsed documents from Qdrant as individual JSON files.

Run from project root:
    python kaggle_data/export_kaggle_data.py

Output: kaggle_data/json_exports/*.json  (one file per document)

Uses QdrantClient directly (no Ollama/embedding dependency).
"""

import sys
import json
import os
import re
import random
from pathlib import Path

# Add project root + backend to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

# ── Config ───────────────────────────────────────────────────────────────────

QDRANT_PATH = str(PROJECT_ROOT / "backend" / "data" / "qdrant_storage")
COLL_DOCUMENTS = "documents"
COLL_CHUNKS = "doc_chunks"
COLL_PROPERTIES = "material_properties"

OUTPUT_DIR = Path(__file__).resolve().parent / "json_exports"
NUM_DOCS = 100
SEED = 42

# ── Helpers ──────────────────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Convert a filename to a safe filesystem name."""
    name = re.sub(r'[^\w\s\-.]', '_', name)
    name = re.sub(r'\s+', '_', name)
    return name[:80]


def parse_json_field(val):
    """Deserialize JSON string fields to Python objects."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val or []


def scroll_all(client, collection, scroll_filter=None, limit=500):
    """Paginate through all results in a collection."""
    all_results = []
    offset = None
    while True:
        results, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=scroll_filter,
            limit=limit,
            offset=offset,
            with_vectors=False,
        )
        all_results.extend(results)
        if next_offset is None:
            break
        offset = next_offset
    return all_results


def get_properties(client, doc_id: str):
    """Get all material properties for a document."""
    results = scroll_all(
        client, COLL_PROPERTIES,
        scroll_filter=Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        )
    )
    return [p.payload for p in results]


def get_source_text(client, doc_id: str) -> str:
    """Reconstruct full text from stored chunks."""
    results = scroll_all(
        client, COLL_CHUNKS,
        scroll_filter=Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        )
    )
    sorted_chunks = sorted(results, key=lambda p: p.payload.get("chunk_index", 0))
    return " ".join(p.payload.get("content", "") for p in sorted_chunks)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"Connecting to Qdrant at: {QDRANT_PATH}")
    if not os.path.exists(QDRANT_PATH):
        print(f"ERROR: Qdrant storage not found at {QDRANT_PATH}")
        sys.exit(1)

    client = QdrantClient(path=QDRANT_PATH)

    # 1. Get all documents
    print("Scrolling all documents...")
    all_docs = scroll_all(client, COLL_DOCUMENTS)
    print(f"Found {len(all_docs)} total documents")

    if len(all_docs) == 0:
        print("ERROR: No documents found in Qdrant")
        sys.exit(1)

    # 2. Select NUM_DOCS balanced by doc_type
    random.seed(SEED)
    tds_docs = [d for d in all_docs if d.payload.get("doc_type") == "tds"]
    paper_docs = [d for d in all_docs if d.payload.get("doc_type") == "paper"]
    other_docs = [d for d in all_docs if d.payload.get("doc_type") not in ("tds", "paper")]

    total = len(all_docs)
    n_tds = max(1, round(NUM_DOCS * len(tds_docs) / total)) if tds_docs else 0
    n_paper = max(1, round(NUM_DOCS * len(paper_docs) / total)) if paper_docs else 0
    n_other = NUM_DOCS - n_tds - n_paper

    random.shuffle(tds_docs)
    random.shuffle(paper_docs)
    random.shuffle(other_docs)

    selected = tds_docs[:n_tds] + paper_docs[:n_paper] + other_docs[:max(0, n_other)]
    # If we still need more, fill from remaining
    if len(selected) < NUM_DOCS:
        remaining = [d for d in all_docs if d not in selected]
        random.shuffle(remaining)
        selected.extend(remaining[:NUM_DOCS - len(selected)])

    selected = selected[:NUM_DOCS]
    print(f"Selected {len(selected)} documents (TDS: {n_tds}, Paper: {n_paper}, Other: {max(0, n_other)})")

    # 3. Export each document
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    exported = 0
    errors = 0

    for i, doc in enumerate(selected):
        payload = doc.payload
        doc_id = payload.get("doc_id", str(doc.id))
        filename = payload.get("filename", f"doc_{i}")

        print(f"  [{i+1}/{len(selected)}] Exporting: {filename[:60]}...", end="", flush=True)

        try:
            # Get properties
            props = get_properties(client, doc_id)

            # Get source text
            source_text = get_source_text(client, doc_id)

            # Build export object
            export = {
                "doc_id": doc_id,
                "filename": filename,
                "doc_type": payload.get("doc_type", "unknown"),
                "material_name": payload.get("material_name", ""),
                "extraction_confidence": payload.get("extraction_confidence", 0),
                "methodology": payload.get("methodology", ""),
                "research_objective": payload.get("research_objective", ""),
                "key_findings": parse_json_field(payload.get("key_findings", [])),
                "processing_conditions": parse_json_field(payload.get("processing_conditions", [])),
                "properties_count": payload.get("properties_count", len(props)),
                "properties": props,
                "source_text": source_text,
            }

            # Write JSON file
            safe_name = sanitize_filename(Path(filename).stem)
            out_path = OUTPUT_DIR / f"{safe_name}.json"

            # Handle duplicates
            if out_path.exists():
                out_path = OUTPUT_DIR / f"{safe_name}_{i}.json"

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(export, f, indent=2, ensure_ascii=False)

            exported += 1
            print(" OK")

        except Exception as e:
            errors += 1
            print(f" ERROR: {e}")

    # 4. Summary
    print(f"\n{'='*60}")
    print(f"Export complete!")
    print(f"  Exported: {exported}")
    print(f"  Errors:   {errors}")
    print(f"  Output:   {OUTPUT_DIR}")
    print(f"\nUpload the '{OUTPUT_DIR.name}' folder to Kaggle as a dataset.")
    print(f"{'='*60}")

    client.close()


if __name__ == "__main__":
    main()
