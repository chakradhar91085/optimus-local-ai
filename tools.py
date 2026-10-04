import inspect
from pydantic import BaseModel, ConfigDict, ValidationError
from datetime import datetime
from typing import Callable, Dict, Any, List, Type

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, dict] = {}
        self._functions: Dict[str, Callable] = {}
        self._models: Dict[str, Type[BaseModel]] = {}

    def register(self, description: str, args_model: Type[BaseModel], permission: str = "READ"):
        """Decorator to register a function as an LLM tool with Pydantic validation."""
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
        """Executes a registered tool after strict validation."""
        if name not in self._functions:
            return f"Error: Tool '{name}' does not exist."
        
        try:
            # Pydantic validation of arguments
            model = self._models[name]
            validated_args = model(**kwargs)
            
            func = self._functions[name]
            result = func(**validated_args.model_dump())
            return str(result)
        except ValidationError as e:
            return f"Error: Invalid arguments for tool '{name}'. Details: {str(e)}"
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"

# Instantiate the global registry
registry = ToolRegistry()

# Argument models (strict validation)
class GetSystemTimeArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')

@registry.register(
    description="Returns the current local system time and date. Use this when the user asks for the time.", 
    args_model=GetSystemTimeArgs,
    permission="READ"
)
def get_system_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
