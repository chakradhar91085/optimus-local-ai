import json
from fastapi import FastAPI, Request
import ollama
import httpx
from tools import registry
from pydantic import ValidationError

app = FastAPI()

MODEL_NAME = "llama3.1:8b"
MAX_ITERATIONS = 8
MAX_TOOL_CALLS = 6

@app.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    messages = data.get("messages", [])
    
    client = ollama.AsyncClient()
    tools = registry.get_all_tool_schemas()
    
    iterations = 0
    tool_calls_count = 0
    
    # Store last tool call to detect immediate duplicates
    last_tool_call_hash = None
    
    while True:
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
            if tool_calls_count >= MAX_TOOL_CALLS:
                messages.append({
                    "role": "tool",
                    "content": "Error: Maximum tool executions per request reached. Synthesize an answer.",
                    "name": "system"
                })
                continue
                
            for tool_call in msg["tool_calls"]:
                function_req = tool_call.get("function", {})
                name = function_req.get("name")
                arguments = function_req.get("arguments", {})
                
                # Check for duplicate
                current_hash = hash(f"{name}:{json.dumps(arguments, sort_keys=True)}")
                if current_hash == last_tool_call_hash:
                    result = "Error: You just called this tool with these exact arguments. Stop repeating and synthesize an answer."
                else:
                    last_tool_call_hash = current_hash
                    print(f"[Agent] LLM requested tool: {name} with args {arguments}")
                    tool_calls_count += 1
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
