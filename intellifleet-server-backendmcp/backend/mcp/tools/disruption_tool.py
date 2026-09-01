from backend.mcp.schemas.disruption_schema import DisruptionInput, DisruptionOutput
from backend.routes.disruption.disruption import UnifiedDisruptionRequest, manage_disruption_function
from fastmcp import FastMCP
from fastapi import HTTPException


# def register_disruption_tools(mcp: FastMCP):
#     """Register disruption management tool"""

#     @mcp.tool()
#     async def manage_disruption_tool(input: DisruptionInput) -> DisruptionOutput:
#         """
#         Manage logistics disruptions in any scenario. 
#         Use this tool when the user mentions the weight disrupted on a route with repair time and disrupted time, and estimated delivery time.
#         """

#         try:
#             print("input......", input)

#             # ── Step 1: Convert input ────────────────────────────────────────
#             raw = input.model_dump()

#             # ── Step 2: Fix schema mismatch (city → warehouse) ──────────────
#             if (
#                 raw.get("operation") == "handle_disruption"
#                 and not raw.get("source_warehouse")
#                 and raw.get("source_city")
#             ):
#                 raw["source_warehouse"] = raw["source_city"]

#             # ── Step 3: Create request object ───────────────────────────────
#             request = UnifiedDisruptionRequest(**raw)

#             # ── Step 4: Execute core logic ──────────────────────────────────
#             try:
#                 result = await manage_disruption(request, input.user_id)
#             except HTTPException as http_exc:
#                 return DisruptionOutput(
#                     message=f"Validation error ({http_exc.status_code}): {http_exc.detail}",
#                     data=None
#                 )

#             # print(f"==>> result: {result}")

#             # ── Step 5: Always return structured output ─────────────────────

#             # ✅ Case 1: Expected dict result
#             if isinstance(result, dict):
#                 return DisruptionOutput(
#                     message=result.get("message", "Operation completed successfully."),
#                     data=result
#                 )

#             # ✅ Case 2: String result
#             if isinstance(result, str):
#                 return DisruptionOutput(
#                     message=result,
#                     data={"raw_result": result}
#                 )

#             # ✅ Case 3: Unexpected type (VERY IMPORTANT fallback)
#             return DisruptionOutput(
#                 message="Operation completed",
#                 data={"raw_result": str(result)}
#             )

#         except Exception as e:
#             return DisruptionOutput(
#                 message=f"Operation failed: {str(e)}",
#                 data=None
#             )

def register_disruption_tools(mcp: FastMCP):
    """Register disruption management tool"""

    @mcp.tool()
    async def manage_disruption_tool(input: DisruptionInput) -> DisruptionOutput:
        """
        Manage logistics disruptions in road or air routes.

        For ROAD disruptions, populate:
        - route_type = 'road'
        - source_warehouse, destination_city, demand_kg
        - disruption_time, required_delivery_time
        - repair_hours (integer or string like '4 hours')
        - disruption_location (optional, e.g. 'near Indore')
        - DO NOT set flight_delay_minutes

        For AIR disruptions, populate:
        - route_type = 'air'
        - source_warehouse, destination_city, demand_kg
        - disruption_time, required_delivery_time
        - flight_delay_minutes (integer minutes, or string like '4 hours' = 240 minutes)
        - DO NOT set repair_hours or disruption_location

        Examples:
        Road: "90kg disruption mumbai→chennai at 7am, 4hr repair, deliver by 8pm"
            → route_type='road', repair_hours=4, flight_delay_minutes=None
        Air: "90kg disruption air route mumbai→chennai at 7am, 4hr delay, deliver by 8pm"
            → route_type='air', flight_delay_minutes=240, repair_hours=None
        """

        try:
            print("input......", input)

            # ────────────────────────────────────────────────────────────────
            # Step 1: Convert Pydantic model → raw dict
            # ────────────────────────────────────────────────────────────────
            raw = input.model_dump()

            # ────────────────────────────────────────────────────────────────
            # Step 2: Directly map to UnifiedDisruptionRequest (1-to-1)
            # ────────────────────────────────────────────────────────────────
            request = UnifiedDisruptionRequest(**raw)

            # ────────────────────────────────────────────────────────────────
            # Step 3: Execute core disruption logic
            # ────────────────────────────────────────────────────────────────

            result = await manage_disruption_function(request, user_id=input.user_id)
            print(f"==>> result:  {result}")


            # ────────────────────────────────────────────────────────────────
            # Step 4: Normalize return types
            # ────────────────────────────────────────────────────────────────

            if isinstance(result, dict):
                return DisruptionOutput(
                    message=result.get("message", "Operation completed successfully."),
                    data=result
                )

            if isinstance(result, str):
                return DisruptionOutput(
                    message=result,
                    data={"raw_result": result}
                )

            return DisruptionOutput(
                message="Operation completed",
                data={"raw_result": str(result)}
            )

        except Exception as e:
            return DisruptionOutput(
                message=f"Operation failed: {str(e)}",
                data=None
            )