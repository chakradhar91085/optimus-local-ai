# MILESTONE 3: Local RAG

## What We Built
Added Document Understanding and RAG (Retrieval-Augmented Generation) capabilities to the assistant while strictly maintaining the Milestone 2 security boundaries.

## Architecture
- **Embedding Model:** `nomic-embed-text` via Ollama's `embed()` API.
- **Vector Storage:** SQLite (zero additional dependencies). Embeddings are stored as JSON strings.
- **Retrieval:** Exact cosine similarity, computed in memory natively in Python.

## Chunking Strategy
- **Target Size:** ~1000 characters.
- **Overlap:** ~200 characters.
- **Method:** Paragraph-aware splitting. It splits by `\n\n` first, gracefully falling back to line and character cuts only if a single paragraph exceeds limits.

## Indexing Limits
- **File Read Limit:** `5 MB` (larger files are skipped safely without partial corruption).
- **Batching:** `32` chunks per embed request to ensure stability.

## Security & Permissions
- **Source Documents:** Remain strictly READ-ONLY.
- **RAG Data:** Application-owned data is stored in `data/rag/index.db`.
- **Git Tracking:** `data/` is added to `.gitignore`.
- **Permissions:** 
  - `search_documents` runs with `READ`.
  - `update_index` runs with `INTERNAL_MAINTENANCE` and can only modify internal database state.
- **Boundary Control:** Every indexed file is rigorously checked through `validate_path()` to absolutely prevent symlink and traversal escapes during indexing.

## Tools Added
1. `update_index`: explicitly indexes or refreshes `assistant_files/`.
2. `search_documents`: retrieves semantic chunks based on user questions.

## Grounding Rules
The system prompt has been extended to require the LLM to strictly cite sources and state "I couldn't find enough evidence" if the chunks are insufficient.
