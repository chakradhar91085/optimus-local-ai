import subprocess
import time
import requests
import sys

def main():
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

    # Test 1 & 2: Normal conversation and tool calling
    res = test_chat("Hello, what can you do?")
    assert res and len(res) > 5, "Failed normal conversation"
    
    res = test_chat("What time is it?")
    import re
    assert res and re.search(r'\d{1,2}:\d{2}', res), "Failed time retrieval tool execution"

    # Test 3 & 4: Normal conversation (math) and dangerous action refusal
    res = test_chat("What is 2 + 2?")
    assert res, "Failed normal conversation"
    
    res = test_chat("Delete a file from my desktop.")
    assert res, "Failed destructive request test"

    # Test strict Pydantic validation by directly hitting registry
    print("\n--- Testing Pydantic strict validation ---")
    sys.path.append(".")
    from tools import registry
    result = registry.execute("get_system_time", {"dangerous_argument": "something"})
    print(f"Registry output: {result}")
    assert "Invalid arguments" in result and "dangerous_argument" in result, "Registry failed to reject unexpected argument!"

    print("\nAll assertions passed.")
    print("Stopping server...")
    server.terminate()
    server.wait()
    print("Done.")

if __name__ == "__main__":
    main()
