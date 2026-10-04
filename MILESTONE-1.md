# MILESTONE 1

## What We Built
The smallest working version of the Local AI Desktop Assistant. This proves the core deterministic agent loop:
`User → Backend → Llama 3.1 → Tool Call → Backend Tool → Llama 3.1 → User`

## Architecture
- **Backend:** FastAPI (Python) serving a REST `/chat` endpoint.
- **LLM Engine:** Ollama running `llama3.1:8b`.
- **Tool Registry:** A simple Python decorator-based registry strictly mapping JSON schema to local Python functions.
- **Validation:** Pydantic is used to strictly enforce and validate tool arguments before execution.
- **Frontend:** Minimal HTML/JS (no frameworks) to prove end-to-end communication.

## Files Created
- `main.py`: The FastAPI backend and agent loop with Ollama error handling.
- `tools.py`: The Tool Registry with strict Pydantic argument validation and `get_system_time()` tool.
- `index.html`: The minimal test UI.
- `test_runner.py`: Automated testing script with assertions.
- `.gitignore`: Ignoring the virtual environment and cached files.
- `requirements.txt`: Locked dependencies.
- `MILESTONE-1.md`: Documentation.

## How to Run It
1. Ensure Ollama is running (`ollama serve`).
2. Open a terminal in this directory.
3. Activate the virtual environment: `.\venv\Scripts\activate`
4. Install dependencies if not already done: `pip install -r requirements.txt`
5. Start the backend: `python main.py`
6. Open your browser and navigate to: `http://127.0.0.1:8000/`

## How the Agent Loop Works
The `/chat` endpoint accepts an array of messages. It passes them to Ollama using `ollama.AsyncClient()`. If Ollama requests a tool call, the backend pauses, validates the tool exists in the registry, validates the arguments strictly with Pydantic, executes the local Python function, appends the result to the messages array, and prompts Ollama again. This continues (up to 5 max iterations) until Ollama returns a final textual answer.

## How Tool Calling Works
Every tool defines a strict Pydantic `BaseModel` that explicitly forbids extra arguments. We provide Ollama with JSON schemas describing available tools. When a tool is needed, Ollama outputs a JSON object. Our `ToolRegistry` executes the corresponding Python function only if validation passes. The LLM never executes shell commands directly.

## Tests Performed
1. Basic conversation: "Hello, what can you do?" -> Handled gracefully.
2. Tool execution: "What time is it?" -> Successfully triggers `get_system_time()`.
3. Non-tool logic: "What is 2 + 2?" -> Answered without a tool call.
4. Hallucination prevention: "Delete a file from my desktop." -> Model is refused because no tool exists.
5. Strict Validation Check: Passed `{"dangerous_argument": "something"}` directly to the registry -> Rejected by Pydantic before execution.
6. Error Handling: Disconnecting Ollama gracefully returns a user-friendly error string instead of crashing.

## Known Limitations
- No streaming. You must wait for the entire agent loop to finish.
- The UI is extremely basic (HTML/JS only).
- Currently no safety approval prompts for WRITE tools because we only have a READ tool.
- Testing for the hard `MAX_ITERATIONS` limit remains a manual/theoretical boundary since setting up complex LLM mocks just for this adds unnecessary early architecture overhead.

## What Comes Next
- Introduce Tauri/React for a real desktop feel.
- Stream tokens back to the UI.
- Implement more complex tools (e.g., file reading).
- Introduce RAG.
