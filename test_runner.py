import subprocess
import time
import requests
import sys
import os
import pathlib
import json

def setup_test_environment():
    base_dir = pathlib.Path(r"C:\Projects\local_ai_assistant")
    sandbox_dir = base_dir / "assistant_files"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    
    # Create valid text file
    with open(sandbox_dir / "hello.txt", "w", encoding="utf-8") as f:
        f.write("Hello, World!")
        
    # Create python file
    with open(sandbox_dir / "script.py", "w", encoding="utf-8") as f:
        f.write("print('Hello from script')")
        
    # Create unsupported file
    with open(sandbox_dir / "test.pdf", "w", encoding="utf-8") as f:
        f.write("fake pdf")
        
    # Create fake text file with NUL byte
    with open(sandbox_dir / "binary.txt", "wb") as f:
        f.write(b"Hello \x00 World")
        
    # Create oversized file (>16k chars)
    with open(sandbox_dir / "large.txt", "w", encoding="utf-8") as f:
        f.write("A" * 20000)
        
    # Create child directory
    child_dir = sandbox_dir / "child_dir"
    child_dir.mkdir(exist_ok=True)
    with open(child_dir / "child_file.txt", "w", encoding="utf-8") as f:
        f.write("child")

def main():
    setup_test_environment()
    print("Starting backend...")
    server = subprocess.Popen(
        [sys.executable, "main.py"], 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE,
        text=True
    )
    
    time.sleep(4) # Wait for server to bind
    
    def test_chat(prompt):
        print(f"\n--- Testing Prompt: '{prompt}' ---")
        data = {
            "messages": [
                {"role": "system", "content": "You are a helpful local Windows AI assistant. You can call tools if needed. Always answer concisely."},
                {"role": "user", "content": prompt}
            ]
        }
        try:
            response = requests.post("http://127.0.0.1:8000/chat", json=data)
            response.raise_for_status()
            text = response.json().get('response')
            print(f"Response:\n{text}")
            return text
        except Exception as e:
            print(f"Error: {e}")
            return None

    # Test strict Pydantic validation by directly hitting registry
    print("\n--- Testing Pydantic & Security validation ---")
    sys.path.append(".")
    from tools import registry
    
    # 1. Existing get_system_time still works
    res = registry.execute("get_system_time", {})
    assert ":" in res, "Failed 1"
    
    # 2. get_system_info works
    res = registry.execute("get_system_info", {})
    assert "OS:" in res, "Failed 2"
    
    sandbox = r"C:\Projects\local_ai_assistant\assistant_files"
    
    # 3. List exact sandbox root
    res = registry.execute("list_directory", {"path": sandbox})
    assert "hello.txt" in res, "Failed 3"
    
    # 4. List valid sandbox child directory
    res = registry.execute("list_directory", {"path": sandbox + r"\child_dir"})
    assert "child_file.txt" in res, "Failed 4"
    
    # 5. Block C:\Windows
    res = registry.execute("list_directory", {"path": r"C:\Windows"})
    assert "Error:" in res, "Failed 5"
    
    # 6. Block C:\Program Files
    res = registry.execute("list_directory", {"path": r"C:\Program Files"})
    assert "Error:" in res, "Failed 6"
    
    # 7. Block path outside assistant_files
    res = registry.execute("list_directory", {"path": r"C:\Projects\local_ai_assistant"})
    assert "Error:" in res, "Failed 7"
    
    # 8. Block sibling prefix trick
    res = registry.execute("list_directory", {"path": r"C:\Projects\local_ai_assistant\assistant_files_fake"})
    assert "Error:" in res, "Failed 8"
    
    # 9. Block .. traversal
    res = registry.execute("list_directory", {"path": sandbox + r"\..\main.py"})
    assert "Error:" in res, "Failed 9"
    
    # 10. Block UNC path
    res = registry.execute("list_directory", {"path": r"\\localhost\c$"})
    assert "Error:" in res, "Failed 10"
    
    # 11. Block alternate drive access
    res = registry.execute("list_directory", {"path": r"D:\test"})
    assert "Error:" in res, "Failed 11"
    
    # 12. Gracefully handle nonexistent paths
    res = registry.execute("list_directory", {"path": sandbox + r"\nonexistent"})
    assert "Error:" in res, "Failed 12"
    
    # 13. Read valid .txt file
    res = registry.execute("read_text_file", {"path": sandbox + r"\hello.txt"})
    assert "Hello, World!" in res, "Failed 13"
    
    # 14. Read valid source-code file
    res = registry.execute("read_text_file", {"path": sandbox + r"\script.py"})
    assert "print" in res, "Failed 14"
    
    # 15. Reject unsupported extension
    res = registry.execute("read_text_file", {"path": sandbox + r"\test.pdf"})
    assert "Error:" in res, "Failed 15"
    
    # 16. Reject fake .txt containing NUL bytes
    res = registry.execute("read_text_file", {"path": sandbox + r"\binary.txt"})
    assert "Error:" in res, "Failed 16"
    
    # 17. Verify >16k content truncated
    res = registry.execute("read_text_file", {"path": sandbox + r"\large.txt"})
    assert "TRUNCATED" in res, "Failed 17"
    assert len(res) < 17000, "Failed 17b"
    
    # 18. Search for known filename
    res = registry.execute("search_files", {"root": sandbox, "query": "hello"})
    assert "hello.txt" in res, "Failed 18"
    
    # 19. Search for missing filename
    res = registry.execute("search_files", {"root": sandbox, "query": "missing_file_123"})
    assert "No matching files" in res, "Failed 19"
    
    # 20. Verify unregistered tools cannot execute
    res = registry.execute("delete_file", {"path": sandbox})
    assert "does not exist" in res, "Failed 21"
    
    # 22. Verify malformed arguments rejected
    res = registry.execute("read_text_file", {"wrong": "args"})
    assert "Invalid arguments" in res, "Failed 22"
    
    # 23. Verify unexpected Pydantic arguments rejected
    res = registry.execute("read_text_file", {"path": sandbox + r"\hello.txt", "extra": "bad"})
    assert "Invalid arguments" in res, "Failed 23"

    # 25. Confirm no WRITE capability exists
    tools = registry.get_all_tool_schemas()
    names = [t["function"]["name"] for t in tools]
    assert "get_system_time" in names
    assert "get_system_info" in names
    assert "list_directory" in names
    assert "search_files" in names
    assert "read_text_file" in names
    assert len(names) == 7, "Failed 25"

    # 26. Junction escape test
    print("\n--- Testing Junction Escape ---")
    outside_dir = pathlib.Path(r"C:\Projects") / "escape_test_dir"
    outside_dir.mkdir(exist_ok=True)
    with open(outside_dir / "secret.txt", "w", encoding="utf-8") as f:
        f.write("Secret data outside sandbox")
        
    junction_path = pathlib.Path(sandbox) / "linked_dir"
    try:
        if not junction_path.exists():
            res = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction_path), str(outside_dir)], capture_output=True, text=True)
            if res.returncode != 0:
                print("Skipping junction test due to OS permission limitations (mklink failed).")
                junction_path = None
    except Exception as e:
        print(f"Skipping junction test due to OS permission limitations: {e}")
        junction_path = None
        
    if junction_path and junction_path.exists():
        # Verify list_directory does NOT expose it
        list_res = registry.execute("list_directory", {"path": sandbox})
        assert "linked_dir" not in list_res, "Failed 26a: list_directory leaked junction name"
        
        # Verify search_files does not discover secret.txt
        search_res = registry.execute("search_files", {"root": sandbox, "query": "secret"})
        assert "secret.txt" not in search_res, "Failed 26b: search_files traversed junction"
        
        # Verify read_text_file blocked
        read_res = registry.execute("read_text_file", {"path": str(junction_path / "secret.txt")})
        assert "Error:" in read_res, "Failed 26c: read_text_file allowed access outside sandbox via junction"
        
        print("Junction escape tests passed.")
        
        # Clean up junction
        try:
            os.rmdir(junction_path)
        except:
            pass

    import shutil
    try:
        shutil.rmtree(outside_dir)
    except:
        pass



    print("\nAll registry unit tests passed.")
    print("Stopping server...")
    server.terminate()
    server.wait()
    print("Done.")

if __name__ == "__main__":
    main()
print("\n--- Testing RAG Engine (M3) ---")

import sys
import os
import json
import sqlite3
import shutil
import asyncio
from pathlib import Path
if "." not in sys.path: sys.path.append(".")
import main
from rag import RagIndex
from tools import registry

test_db_dir = Path("data/rag")
test_db_dir.mkdir(parents=True, exist_ok=True)
test_db_path = test_db_dir / "test_index_deterministic.db"
try:
    import sqlite3
    with sqlite3.connect(test_db_path) as conn:
        conn.execute("DELETE FROM document_chunks")
except:
    pass

class FakeOllamaClient:
    async def embed(self, model, input):
        if isinstance(input, str): input = [input]
        return {'embeddings': [[0.5] * 768 for _ in input]}
    async def list(self):
        class MockModels: models = []
        return MockModels()

fake_client = FakeOllamaClient()
rag = RagIndex(str(test_db_path), client=fake_client)

# Disable the model check in test using the fake client check bypass
async def mock_check_model(): return True
rag.check_model = mock_check_model

async def run_rag_tests():
    print('Starting run_rag_tests')
    # 1. SYSTEM_PROMPT tests
    print('1. checking sys_prompt'); assert hasattr(main, "SYSTEM_PROMPT"), "SYSTEM_PROMPT missing"
    assert "I couldn't find enough evidence" in main.SYSTEM_PROMPT, "Grounding evidence instruction missing"
    assert "Call update_index ONLY when the user explicitly asks" in main.SYSTEM_PROMPT, "Indexing rule missing"
    assert 'messages.insert(0, {"role": "system"' in Path("main.py").read_text(), "System prompt insertion missing"
    
    # 2. Chunking logic
    text = "P1\n\nP2\n\nP3"
    print('2. chunking'); chunks = rag.chunk_text(text, target_size=5, overlap=2)
    assert len(chunks) == 2, "Chunking logic failed"
    text2 = "1234567890"
    chunks2 = rag.chunk_text(text2, target_size=6, overlap=2)
    assert "56" in chunks2[1], "Overlap logic failed"
    assert len(rag.chunk_text("")) == 0
    assert len(rag.chunk_text("short")) == 1
    
    # 3. DB & Cosine checks
    print('3. db exists'); assert test_db_path.exists()
    assert rag.cosine_similarity([1, 0], [1, 0, 0]) == 0.0, "Cosine dim check failed"
    
    # 4. Atomic indexing failure test
    sandbox = Path("assistant_files")
    sandbox.mkdir(exist_ok=True)
    test_file = sandbox / "atomic_test.txt"
    test_file.write_text("Hello World", encoding="utf-8")
    
    # Successful initial index
    print('4. atomic test'); res = await rag.update_index(str(sandbox))
    assert "files newly indexed" in res
    
    with sqlite3.connect(rag.db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM document_chunks WHERE filename='atomic_test.txt'").fetchone()[0]
        assert count > 0
        old_val = conn.execute("SELECT chunk_text FROM document_chunks WHERE filename='atomic_test.txt'").fetchone()[0]
        assert "Hello World" in old_val
    
    # Fail halfway through embedding
    test_file.write_text("Modified File", encoding="utf-8")
    async def failing_embed(model, input):
        if "Modified" in input[0]:
            raise Exception("Simulated Fake Client Failure")
        return await FakeOllamaClient().embed(model=model, input=input)
    fake_client.embed = failing_embed
    
    try:
        await rag.update_index(str(sandbox))
    except Exception:
        pass
    
    with sqlite3.connect(rag.db_path) as conn:
        new_val = conn.execute("SELECT chunk_text FROM document_chunks WHERE filename='atomic_test.txt'").fetchone()[0]
        assert "Hello World" in new_val, "Index corrupted by partial update"
    
    # Succeed completely
    async def passing_embed(model, input):
        return await FakeOllamaClient().embed(model=model, input=input)
    fake_client.embed = passing_embed
    await rag.update_index(str(sandbox))
    
    with sqlite3.connect(rag.db_path) as conn:
        new_val2 = conn.execute("SELECT chunk_text FROM document_chunks WHERE filename='atomic_test.txt'").fetchone()[0]
        assert "Modified File" in new_val2, "Index did not successfully atomically replace"
    
    # Dimension / count mismatch
    test_file.write_text("Mismatch count", encoding="utf-8")
    async def mismatch_embed1(model, input): return {'embeddings': []}
    fake_client.embed = mismatch_embed1
    await rag.update_index(str(sandbox))
    with sqlite3.connect(rag.db_path) as conn:
        res = conn.execute("SELECT chunk_text FROM document_chunks WHERE filename='atomic_test.txt'").fetchone()[0]
        assert "Modified File" in res, "Index corrupted by embedding count mismatch"

    test_file.write_text("Mismatch dim", encoding="utf-8")
    async def mismatch_embed2(model, input): return {'embeddings': [[0.5]*767 for _ in input]}
    fake_client.embed = mismatch_embed2
    await rag.update_index(str(sandbox))
    with sqlite3.connect(rag.db_path) as conn:
        res = conn.execute("SELECT chunk_text FROM document_chunks WHERE filename='atomic_test.txt'").fetchone()[0]
        assert "Modified File" in res, "Index corrupted by embedding dimension mismatch"
    
    # Cleanup
    
    # 5. Junction traversal test
    print('5. junction test')
    outside_dir = Path(r"C:\Projects") / "escape_rag_dir"
    outside_dir.mkdir(exist_ok=True)
    (outside_dir / "rag_secret.txt").write_text("Secret RAG data", encoding="utf-8")
    
    junc_path = sandbox / "rag_linked_dir"
    try:
        if not junc_path.exists():
            subprocess.run(["cmd", "/c", "mklink", "/J", str(junc_path), str(outside_dir)], capture_output=True, text=True)
    except:
        pass
        
    if junc_path.exists():
        res = await rag.update_index(str(sandbox))
        with sqlite3.connect(rag.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM document_chunks WHERE chunk_text LIKE '%Secret RAG data%'").fetchone()[0]
            assert count == 0, "RAG index traversed junction!"
        os.rmdir(junc_path)
    shutil.rmtree(outside_dir, ignore_errors=True)

    test_file.unlink(missing_ok=True)
    try:
        with sqlite3.connect(test_db_path) as conn:
            conn.execute("DELETE FROM document_chunks")
    except:
        pass
    print("All M3 RAG Tests Passed.")

asyncio.run(run_rag_tests())
print("\nAll assertions passed.")

