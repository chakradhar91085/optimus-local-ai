import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import ollama
import httpx
from pydantic import BaseModel
from typing import List, Dict, Any

from tools import registry

app = FastAPI()

MODEL_NAME = "llama3.1:8b"
MAX_ITERATIONS = 5

class Message(BaseModel):
    role: str
    content: str | None = None
    tool_calls: List[Dict[str, Any]] | None = None

class ChatRequest(BaseModel):
    messages: List[Message]

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    with open("index.html", "r") as f:
        return f.read()

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    messages = [m.model_dump(exclude_none=True) for m in request.messages]
    tools = registry.get_all_tool_schemas()
    
    client = ollama.AsyncClient()
    
    iterations = 0
    while iterations < MAX_ITERATIONS:
        iterations += 1
        
        try:
            response = await client.chat(
                model=MODEL_NAME,
                messages=messages,
                tools=tools
            )
        except httpx.ConnectError:
            print("[Agent] Error: Unable to connect to Ollama.")
            return {"response": "Error: Unable to connect to the local AI model. Make sure Ollama is running."}
        except httpx.TimeoutException:
            print("[Agent] Error: Ollama request timed out.")
            return {"response": "The local AI model took too long to respond. Please try again."}
        except ollama.ResponseError as e:
            print(f"[Agent] Ollama API Error: {e}")
            return {"response": f"Error: AI model returned an API error. {e}"}
        except Exception as e:
            print(f"[Agent] Unexpected Error communicating with Ollama: {e}")
            return {"response": "Error: An unexpected error occurred while communicating with the AI model."}
        
        msg = response.get("message", {})
        messages.append(msg)
        
        if "tool_calls" in msg and msg["tool_calls"]:
            for tool_call in msg["tool_calls"]:
                function_req = tool_call.get("function", {})
                name = function_req.get("name")
                arguments = function_req.get("arguments", {})
                
                print(f"[Agent] LLM requested tool: {name} with args {arguments}")
                
                result = registry.execute(name, arguments)
                print(f"[Agent] Tool result: {result}")
                
                messages.append({
                    "role": "tool",
                    "content": result,
                    "name": name
                })
                
            continue
        else:
            break
            
    if iterations >= MAX_ITERATIONS:
        return {"response": "Error: Maximum agent iterations reached."}
        
    return {"response": messages[-1].get("content", "")}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
