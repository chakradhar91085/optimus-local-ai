import inspect
import platform
import sys
import os
from pydantic import BaseModel, ConfigDict, ValidationError
from datetime import datetime
from typing import Callable, Dict, Any, List, Type
from security import validate_path

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, dict] = {}
        self._functions: Dict[str, Callable] = {}
        self._models: Dict[str, Type[BaseModel]] = {}

    def register(self, description: str, args_model: Type[BaseModel], permission: str = "READ"):
        def decorator(func: Callable):
            name = func.__name__
            self._functions[name] = func
            self._models[name] = args_model
            
            schema = args_model.model_json_schema()
            
            self._tools[name] = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": schema.get("properties", {}),
                        "required": schema.get("required", [])
                    }
                }
            }
            return func
        return decorator

    def get_all_tool_schemas(self) -> List[dict]:
        return list(self._tools.values())

    def execute(self, name: str, kwargs: dict) -> str:
        if name not in self._functions:
            return f"Error: Tool '{name}' does not exist."
        
        try:
            model = self._models[name]
            validated_args = model(**kwargs)
            func = self._functions[name]
            result = func(**validated_args.model_dump())
            # Convert result to string and enforce result size limit
            result_str = str(result)
            if len(result_str) > 50000:
                result_str = result_str[:50000] + "\n\n[...TRUNCATED: Tool result exceeded 50,000 characters]"
            return result_str
        except ValidationError as e:
            return f"Error: Invalid arguments for tool '{name}'. Details: {str(e)}"
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"

registry = ToolRegistry()

class GetSystemTimeArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')

@registry.register(
    description="Returns the current local system time and date.", 
    args_model=GetSystemTimeArgs,
    permission="READ"
)
def get_system_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class GetSystemInfoArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')

@registry.register(
    description="Returns basic harmless system information (OS, version, Python version).", 
    args_model=GetSystemInfoArgs,
    permission="READ"
)
def get_system_info() -> str:
    return f"OS: {platform.system()}\nRelease: {platform.release()}\nMachine: {platform.machine()}\nPython: {sys.version}"

class ListDirectoryArgs(BaseModel):
    path: str
    model_config = ConfigDict(extra='forbid')

@registry.register(
    description="Lists files and folders inside an allowed sandbox directory.", 
    args_model=ListDirectoryArgs,
    permission="READ"
)
def list_directory(path: str) -> str:
    try:
        safe_path = validate_path(path, expected_type="dir")
        entries = []
        with os.scandir(safe_path) as it:
            for entry in it:
                # Skip hidden files
                if entry.name.startswith("."):
                    continue
                if entry.is_symlink() or (hasattr(entry, 'is_junction') and entry.is_junction()):
                    continue
                if entry.is_symlink() or (hasattr(entry, 'is_junction') and entry.is_junction()):
                    continue
                type_str = "DIR " if entry.is_dir() else "FILE"
                entries.append(f"[{type_str}] {entry.name}")
        entries.sort()
        if len(entries) > 100:
            entries = entries[:100] + ["\n[...TRUNCATED: Exceeded 100 entries]"]
        return "\n".join(entries) if entries else "Directory is empty."
    except Exception as e:
        return str(e)

class SearchFilesArgs(BaseModel):
    root: str
    query: str
    model_config = ConfigDict(extra='forbid')

@registry.register(
    description="Recursively searches for filenames inside an allowed directory. Searches filenames only, case-insensitive.", 
    args_model=SearchFilesArgs,
    permission="READ"
)
def search_files(root: str, query: str) -> str:
    try:
        safe_root = validate_path(root, expected_type="dir")
        results = []
        skip_dirs = {".git", "node_modules", "venv", "__pycache__"}
        query_lower = query.lower()
        
        def search_recursive(current_path, depth):
            if depth > 5 or len(results) >= 50:
                return
            try:
                with os.scandir(current_path) as it:
                    for entry in it:
                        if entry.name.startswith("."):
                            continue
                        if entry.is_symlink() or (hasattr(entry, 'is_junction') and entry.is_junction()):
                            continue
                        if entry.is_dir() and entry.name in skip_dirs:
                            continue
                        if query_lower in entry.name.lower():
                            results.append(str(entry.path))
                        if entry.is_dir() and len(results) < 50:
                            search_recursive(entry.path, depth + 1)
            except Exception:
                pass
                
        search_recursive(safe_root, 1)
        
        if not results:
            return "No matching files found."
        
        out = "\n".join(results)
        if len(results) >= 50:
            out += "\n\n[...TRUNCATED: Maximum 50 results reached]"
        return out
    except Exception as e:
        return str(e)

class ReadTextFileArgs(BaseModel):
    path: str
    model_config = ConfigDict(extra='forbid')

@registry.register(
    description="Reads the contents of a supported text file within the sandbox (.txt, .md, .json, .csv, .py, .js, .ts, .html, .css).", 
    args_model=ReadTextFileArgs,
    permission="READ"
)
def read_text_file(path: str) -> str:
    try:
        safe_path = validate_path(path, expected_type="file")
        allowed_exts = {".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".html", ".css"}
        if safe_path.suffix.lower() not in allowed_exts:
            return "Error: Unsupported file extension."
            
        with open(safe_path, "rb") as f:
            chunk = f.read(1024 * 1024) # read max 1MB
            
        if b'\x00' in chunk:
            return "Error: File appears to be binary."
            
        text = chunk.decode('utf-8', errors='replace')
        if len(text) > 16000:
            text = text[:16000] + "\n\n[...TRUNCATED: additional content was not returned]"
            
        return text
    except Exception as e:
        return str(e)


import asyncio
from pydantic import BaseModel, ConfigDict
from rag import RagIndex

DB_PATH = r"C:\Projects\local_ai_assistant\data\rag\index.db"
rag_index = RagIndex(DB_PATH)
SANDBOX = r"C:\Projects\local_ai_assistant\assistant_files"

class UpdateIndexArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')

@registry.register(
    description="Updates the internal document index by scanning assistant_files. Call this ONLY when explicitly asked to index, refresh, update, or process documents.", 
    args_model=UpdateIndexArgs,
    permission="INTERNAL_MAINTENANCE"
)
def update_index() -> str:
    return asyncio.run(rag_index.update_index(SANDBOX))

class SearchDocumentsArgs(BaseModel):
    query: str
    model_config = ConfigDict(extra='forbid')

@registry.register(
    description="Semantically searches the indexed documents for relevant information. Use this to answer questions about the user's documents.", 
    args_model=SearchDocumentsArgs,
    permission="READ"
)
def search_documents(query: str) -> str:
    return asyncio.run(rag_index.search(query))
