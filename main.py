import json
import uuid
import time
import asyncio
from typing import Dict, Literal
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, ConfigDict
import ollama
import httpx
from tools import registry
from security import validate_write_path, get_resolved_allowed_root

app = FastAPI()

MODEL_NAME = "llama3.1:8b"
MAX_ITERATIONS = 8
MAX_TOOL_CALLS = 6

SYSTEM_PROMPT = """You are a helpful and secure local Windows AI assistant. You have access to tools to interact with the local system.
Always adhere to these strict security and grounding rules:

1. For questions about indexed documents, use the search_documents tool to retrieve evidence.
2. Base document answers STRICTLY on retrieved evidence.
3. If retrieved evidence is insufficient, say EXACTLY: "I couldn't find enough evidence in the indexed documents."
4. Do NOT invent facts supposedly contained in documents.
5. Include simple source references using the returned metadata (e.g. [File: ...]).
6. Do NOT call update_index automatically during ordinary questions.
7. Call update_index ONLY when the user explicitly asks to index documents, refresh the index, update the index, or process newly added documents.
8. No arbitrary command execution.
9. No filesystem access outside approved tools.
10. You have no direct or autonomous WRITE access. Files may only be modified through registered WRITE tools after explicit human approval, and only inside the approved assistant_files sandbox.
"""

class PendingAction(BaseModel):
    action_id: str
    tool_name: str
    validated_arguments: dict
    permission_level: str
    description: str
    relative_path: str
    bounded_preview: str
    created_at: float
    expires_at: float
    status: Literal["PENDING", "APPROVED", "DENIED", "EXECUTING", "EXECUTED", "EXPIRED", "FAILED"]
    conversation_state: dict

pending_actions: Dict[str, PendingAction] = {}
action_locks: Dict[str, asyncio.Lock] = {}

class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str

def log_audit(action_id: str, tool_name: str, relative_path: str, status: str):
    import pathlib
    import datetime
    audit_file = pathlib.Path("data/audit.log")
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "action_id": action_id,
        "tool_name": tool_name,
        "relative_path": relative_path,
        "status": status
    }
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

async def run_agent_loop(messages: list, iterations: int = 0, tool_calls_count: int = 0, last_tool_call_hash: int = None):
    client = ollama.AsyncClient()
    tools = registry.get_all_tool_schemas()
    
    while True:
        iterations += 1
        if iterations > MAX_ITERATIONS:
            return {"response": "Error: Maximum agent iterations reached."}
            
        try:
            response = await client.chat(
                model=MODEL_NAME,
                messages=messages,
                tools=tools
            )
        except Exception as e:
            return {"response": f"Error: AI model communication failed: {e}"}
            
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
                
            # Process tool calls
            for tool_call in msg["tool_calls"]:
                function_req = tool_call.get("function", {})
                name = function_req.get("name")
                arguments = function_req.get("arguments", {})
                
                current_hash = hash(f"{name}:{json.dumps(arguments, sort_keys=True)}")
                if current_hash == last_tool_call_hash:
                    messages.append({
                        "role": "tool",
                        "content": "Error: You just called this tool with these exact arguments. Stop repeating.",
                        "name": name
                    })
                    continue
                    
                last_tool_call_hash = current_hash
                tool_calls_count += 1
                
                try:
                    validated_args = registry.validate_args(name, arguments)
                except Exception as e:
                    messages.append({
                        "role": "tool",
                        "content": f"Error: Validation failed: {e}",
                        "name": name
                    })
                    continue
                    
                permission = registry.get_permission(name)
                
                if permission == "WRITE":
                    try:
                        operation = "create" if name == "create_text_file" else "append"
                        resolved_target = validate_write_path(validated_args.get("path", ""), operation=operation)
                        sandbox_root = get_resolved_allowed_root()
                        rel_path = str(resolved_target.relative_to(sandbox_root)).replace("\\", "/")
                    except Exception as e:
                        messages.append({
                            "role": "tool",
                            "content": f"Error: Write path/security validation failed: {str(e)}",
                            "name": name
                        })
                        continue
                        
                    action_id = uuid.uuid4().hex
                    content_str = validated_args.get("content", "")
                    bounded_preview = content_str[:200] + ("..." if len(content_str) > 200 else "")
                    
                    action = PendingAction(
                        action_id=action_id,
                        tool_name=name,
                        validated_arguments=json.loads(json.dumps(validated_args)),
                        permission_level=permission,
                        description=f"{name}",
                        relative_path=rel_path,
                        bounded_preview=bounded_preview,
                        created_at=time.time(),
                        expires_at=time.time() + 900,
                        status="PENDING",
                        conversation_state={
                                                "messages": json.loads(json.dumps(messages, default=lambda o: dict(o) if hasattr(o, "keys") else (o.model_dump() if hasattr(o, "model_dump") else str(o)))),
                            "iterations": iterations,
                            "tool_calls_count": tool_calls_count,
                            "last_tool_call_hash": last_tool_call_hash
                        }
                    )
                    pending_actions[action_id] = action
                    action_locks[action_id] = asyncio.Lock()
                    
                    return {
                        "status": "APPROVAL_REQUIRED",
                        "action": {
                            "action_id": action_id,
                            "tool_name": name,
                            "description": action.description,
                            "relative_path": action.relative_path,
                            "character_count": len(content_str),
                            "bounded_preview": action.bounded_preview
                        }
                    }
                else:
                    # Execute immediately
                    try:
                        result = registry.execute(name, validated_args)
                    except Exception as e:
                        result = f"Error: {str(e)}"
                    
                    messages.append({
                        "role": "tool",
                        "content": result,
                        "name": name
                    })
            continue
        else:
            break
            
    return {"response": messages[-1].get("content", "")}

@app.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    messages = data.get("messages", [])
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    return await run_agent_loop(messages)

@app.post("/api/action/approve")
async def approve_action(req: ActionRequest):
    action_id = req.action_id
    if action_id not in pending_actions:
        raise HTTPException(status_code=404, detail="Action not found")
        
    action = pending_actions[action_id]
    lock = action_locks.get(action_id)
    
    if not lock:
        raise HTTPException(status_code=500, detail="Lock missing")
        
    async with lock:
        if action.status != "PENDING":
            raise HTTPException(status_code=400, detail=f"Action is in state {action.status}")
            
        if time.time() > action.expires_at:
            action.status = "EXPIRED"
            log_audit(action_id, action.tool_name, action.relative_path, "EXPIRED")
            raise HTTPException(status_code=400, detail="Action has expired")
            
        action.status = "EXECUTING"
        
    try:
        # Immutable args
        result = registry.execute(action.tool_name, action.validated_arguments)
        action.status = "EXECUTED"
        log_audit(action_id, action.tool_name, action.relative_path, "EXECUTED")
    except Exception as e:
        result = f"Error: {str(e)}"
        action.status = "FAILED"
        log_audit(action_id, action.tool_name, action.relative_path, "FAILED")
        
    # Resume the agent
    msgs = action.conversation_state["messages"]
    msgs.append({"role": "tool", "content": result, "name": action.tool_name})
    
    del pending_actions[action_id]
    del action_locks[action_id]
    
    res = await run_agent_loop(
        messages=msgs, 
        iterations=action.conversation_state["iterations"], 
        tool_calls_count=action.conversation_state["tool_calls_count"], 
        last_tool_call_hash=action.conversation_state["last_tool_call_hash"]
    )
    if res.get("status") == "APPROVAL_REQUIRED":
        return res
    return {"status": "success", "result": res.get("response")}

@app.post("/api/action/reject")
async def reject_action(req: ActionRequest):
    action_id = req.action_id
    if action_id not in pending_actions:
        raise HTTPException(status_code=404, detail="Action not found")
        
    action = pending_actions[action_id]
    lock = action_locks.get(action_id)
    
    async with lock:
        if action.status != "PENDING":
            raise HTTPException(status_code=400, detail=f"Action is in state {action.status}")
            
        action.status = "DENIED"
        log_audit(action_id, action.tool_name, action.relative_path, "DENIED")
        
    msgs = action.conversation_state["messages"]
    msgs.append({"role": "tool", "content": "USER REJECTED ACTION. Try a different approach.", "name": action.tool_name})
    
    del pending_actions[action_id]
    del action_locks[action_id]
    
    res = await run_agent_loop(
        messages=msgs, 
        iterations=action.conversation_state["iterations"], 
        tool_calls_count=action.conversation_state["tool_calls_count"], 
        last_tool_call_hash=action.conversation_state["last_tool_call_hash"]
    )
    if res.get("status") == "APPROVAL_REQUIRED":
        return res
    return {"status": "success", "result": res.get("response")}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
