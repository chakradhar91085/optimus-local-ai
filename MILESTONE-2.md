# MILESTONE 2

## What We Built
Added safe READ-ONLY local filesystem capabilities to the assistant. The assistant now has permission to look at system information, list directories, search files by name, and read text-based files, but ONLY within a dedicated sandbox.

## Tools Added
1. `get_system_info`: Returns OS, version, machine type, and Python version.
2. `list_directory`: Lists up to 100 entries inside an allowed directory.
3. `search_files`: Recursively searches for filenames inside an allowed directory.
4. `read_text_file`: Reads text from supported extensions (.txt, .md, .json, .csv, .py, .js, .ts, .html, .css).

## Sandbox Design
**The assistant currently has READ-only access ONLY to:**
`C:\Projects\local_ai_assistant\assistant_files`

## Allowed-Root Security
All filesystem access is routed through a central `security.py` module. The `validate_path` function explicitly rejects:
- Paths outside the sandbox
- Sibling directories masquerading with prefix tricks (e.g., `assistant_files_fake`)
- `..` traversal attempts
- UNC, network, and device paths (`\\`, `//`)
- Drive-relative paths (`C:folder`)
- Access to sensitive locations (`C:\Windows`, `Program Files`, etc. by virtue of the sandbox)

It safely uses `pathlib.Path.resolve(strict=True)` to force strict absolute paths, defeating symlinks, junctions, and relative escapes.

## Limits
- **Read Limits:** Reads at most approximately 1 MB from disk and returns at most 16,000 characters to the LLM (truncated if exceeded). It does NOT enforce a 250 KB hard rejection. Files with NUL bytes (`\x00`) are blocked.
- **Search Limits:** Max depth of 5, max 50 results. Hidden and internal folders (`.git`, `node_modules`, `venv`, `__pycache__`) are skipped.
- **Agent Loop Limits:** Increased `MAX_ITERATIONS` to 8 and added `MAX_TOOL_CALLS = 6`. Introduced immediate duplicate tool call prevention.

## Tests
Expanded `test_runner.py` with 25 mandatory assertions covering allowed paths, path traversal escapes, unsupported extensions, large files, and binary detection.

## Known Limitations
- Content search is intentionally unsupported.
- Read access is strictly locked to one directory. User-configurable paths will come in future milestones.
- Write, delete, or rename tools are explicitly NOT included.
