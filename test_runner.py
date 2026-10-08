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
    assert len(names) == 5, "Failed 25"

    
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


