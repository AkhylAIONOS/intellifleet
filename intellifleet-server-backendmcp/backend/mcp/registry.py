
#backend/mcp/registry.py
"""
Simple tool registry - No complex MCP, just register and execute
"""

TOOL_REGISTRY = {}

def register_tool(tool_name: str):
    """Decorator to register a tool"""
    def decorator(tool_class):
        TOOL_REGISTRY[tool_name] = tool_class
        print(f"✅ Registered tool: {tool_name}")
        return tool_class
    return decorator