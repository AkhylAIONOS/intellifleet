##### MCP Client code without http request ############
# backend/mcp/tool_loader.py
from typing import List, get_type_hints
from langchain.tools import StructuredTool
from fastmcp.tools.tool import FunctionTool
from backend.mcp.server import mcp
import inspect

from pydantic.v1 import PrivateAttr   # 🔥 IMPORTANT


class MCPToolWrapper(StructuredTool):

    _mcp_tool = PrivateAttr()
    _input_model = PrivateAttr()

    def __init__(self, mcp_tool: FunctionTool):

        fn = mcp_tool.fn
        sig = inspect.signature(fn)

        params = list(sig.parameters.values())
        if len(params) != 1:
            raise ValueError(
                f"Tool {mcp_tool.key} must have exactly one parameter"
            )

        param_name = params[0].name
        type_hints = get_type_hints(fn)
        input_model = type_hints.get(param_name)

        super().__init__(
            name=mcp_tool.key,
            description=mcp_tool.description,
            args_schema=input_model,
            func=self._run_sync,
            coroutine=self._run_async,
            return_direct=False,
        )

        # ✅ now allowed
        self._mcp_tool = mcp_tool
        self._input_model = input_model

    async def _run_async(self, **kwargs):
        model_instance = self._input_model(**kwargs)
        result = await self._mcp_tool.fn(model_instance)

        if hasattr(result, "model_dump"):
            return result.model_dump()

        return result

    def _run_sync(self, **kwargs):
        import asyncio
        return asyncio.run(self._run_async(**kwargs))


async def load_mcp_tools() -> List[StructuredTool]:

    tools_dict = await mcp.get_tools()

    wrapped = []

    for key, tool in tools_dict.items():
        if isinstance(tool, FunctionTool):
            wrapped.append(MCPToolWrapper(tool))
            print(f"✅ Loaded tool: {key}")

    print(f"\n🚀 Total tools loaded: {len(wrapped)}")
    return wrapped





# #backend/mcp/tools/tool_client.py
# from typing import List
# from langchain.tools import BaseTool, StructuredTool
# from fastmcp import Client
# import asyncio
# from backend.config.config import settings
# import inspect

# class MCPToolWrapper(StructuredTool):
#     """Enhanced wrapper for MCP tools with proper schema support"""
    
#     def __init__(self, mcp_tool):
#         # Extract schema information from MCP tool
#         name = mcp_tool.name
#         description = mcp_tool.description or f"Tool: {name}"
        
#         # Get input/output schemas from MCP tool
#         args_schema = None
#         if hasattr(mcp_tool, 'args_schema'):
#             args_schema = mcp_tool.args_schema
        
#         # Create the structured tool
#         super().__init__(
#             name=name,
#             description=description,
#             args_schema=args_schema,
#             func=self._execute_sync,
#             coroutine=self._execute_async,
#             return_direct=False
#         )
        
#         self.mcp_tool = mcp_tool
#         self._validate_schema()
    
#     def _validate_schema(self):
#         """Validate that tool has proper schemas"""
#         if not self.args_schema:
#             print(f"⚠️ Warning: Tool '{self.name}' has no input schema")
    
#     async def _execute_async(self, **kwargs):
#         """Async execution with schema validation"""
#         try:
#             # MCP tools expect structured input
#             if self.args_schema:
#                 # Validate against schema
#                 validated = self.args_schema(**kwargs)
#                 # Extract user_id if present in kwargs
#                 if 'user_id' in kwargs:
#                     # Pass as structured argument
#                     return await self.mcp_tool(validated)
#                 else:
#                     # Pass as kwargs
#                     return await self.mcp_tool(**validated.dict())
#             else:
#                 return await self.mcp_tool(**kwargs)
#         except Exception as e:
#             return {"error": str(e), "tool": self.name}
    
#     def _execute_sync(self, **kwargs):
#         """Sync execution (fallback)"""
#         import asyncio
#         return asyncio.run(self._execute_async(**kwargs))
    
#     def get_tool_metadata(self) -> dict:
#         """Get structured metadata about the tool"""
#         metadata = {
#             "name": self.name,
#             "description": self.description,
#             "has_schema": self.args_schema is not None,
#             "input_fields": [],
#             "output_fields": []
#         }
        
#         if self.args_schema:
#             schema_dict = self.args_schema.schema()
#             metadata["input_fields"] = list(schema_dict.get("properties", {}).keys())
        
#         return metadata
