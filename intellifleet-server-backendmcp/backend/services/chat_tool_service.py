# ==============================================
# MCP + LANGGRAPH INTEGRATION
# ==============================================
import logging
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

# -------------------------
# AUTH
# -------------------------
from backend.routes.auth import get_current_user

# -------------------------
# CONFIG / LOGGER
# -------------------------
from backend.config.logger import logger
from backend.config.redis import delete_data

# -------------------------
# MODELS
# -------------------------
from backend.models.agentSchema import *
from backend.models.models import ChatPrompt
from backend.models.vechileSchema import (
    VehicleAssignmentRequest,
    ResetSingleVehicleRequest,
    VehicleCompleteRequest,
)
from backend.models.routeSchema import (
    RemoveRouteRequest,
    AlternativeRouteRequest,
)
from backend.models.airRouteSchema import *

# -------------------------
# DATABASE / HELPERS
# -------------------------
from backend.database.database import *

# -------------------------
# ROUTE / SERVICE FUNCTIONS
# -------------------------
from backend.routes.api import unified_chat_endpoint_function, get_chat_memory
from backend.routes.googleRoute import *
from backend.routes.vehicle_api import (
    assign_vehicle_to_route_function,
    reset_single_vehicle_function,
    complete_vehicle_route_function,
)
from backend.routes.airRoute import (
    combined_route_function,
    remove_multimodal_route_function,
    generate_hub_to_capital_routes,
)
from backend.routes.multimodalVehicle import *
from backend.routes.warehouse import set_warehouse_active_status
from backend.routes.clearAll import clear_all_routes_function

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self): 
        pass

    # async def process_message(self, chat_request, user_id: int):
    #     """Main orchestrator for AI chat"""

    #     try:
    #         intent_result = await unified_chat_endpoint_function(
    #             chat_prompt=ChatPrompt(
    #                 prompt=chat_request.message
    #             ),
    #             user_id=user_id
    #         )

    #         if not isinstance(intent_result, dict):
    #             raise ValueError("Invalid response from unified chat")

    #         logger.debug("Intent result: %s", intent_result)

    #     except Exception as e:
    #         logger.exception("Unified chat failed")
    #         return {
    #             "success": False,
    #             "response": "Sorry, something went wrong calling the AI.",
    #             "actions": [],
    #         }

    #     # -------------------------
    #     # CONFIDENCE CHECK
    #     # -------------------------
    #     confidence = intent_result.get("confidence", 0.0)
    #     if confidence < 0.3:
    #         intent_result["intent"] = "help"
    #         intent_result["reply"] = (
    #             "I'm not sure I understood that. Could you rephrase?"
    #         )

    #     # -------------------------
    #     # INTENT HANDLING
    #     # -------------------------
    #     intent = intent_result.get("intent", "help")
    #     params = intent_result.get("parameters", {})
    #     reply = intent_result.get("reply", "")

    #     handlers = {
    #         "plan_route": self._handle_plan_route,
    #         "assign_vehicle": self._handle_assign_vehicle,
    #         "alternative_route": self._handle_alternative_route,
    #         "remove_route": self._handle_remove_route,
    #         "stop_vehicle": self._handle_reset_single_vehicle,
    #         "clear_map": self._handle_clear_all_routes,
    #         "satellite_view": self._handle_satellite_view,
    #         "street_view": self._handle_street_view,
    #         "clear_chat": self._handle_clear_chat,
    #         "help": self._handle_help,
    #         "complete_vehicle_route": self._complete_vehicle_route,
    #         "multimodal_route": self._handle_multimodal_route,
    #         "remove_multimodal_route": self._handle_remove_multimodal_route,
    #         "reset_all_vehicles": self._handle_reset_all_vehicles,
    #         "assign_vehicle_multimodal": self._handle_multimodal_assign_vehicle,
    #         "connect_hub": self._handle_hub_to_capital_routes,
    #         "warehouse_status_update": self._handle_warehouse_status,
    #         "fetch_routes": self._handle_fetch_routes,
    #         "vehicle_status_update": self._handle_vehicle_status,
    #         "assign_plane": self._handle_assign_plane

    #     }


    #     handler = handlers.get(intent, self._handle_help)
    #     response_data = await handler(
            
    #         message=chat_request.message,
    #         params=params,
    #         user_id=user_id,
    #         reply=reply
    #     )

    #     # -------------------------
    #     # FINAL RESPONSE
    #     # -------------------------
    #     return {
    #         "success": True,
    #         "response": response_data["response_text"],
    #         "actions": response_data.get("actions", []),
    #     }


    # # -------------------------
    # # INTENT HANDLERS
    # # -------------------------
    
    
    async def _handle_plan_route(self, message, params, user_id, reply=None):
        """
        Handles route planning using Google API with Redis + DB caching.
        Supports multi-stop routes if intermediate_locations are provided.
        """
        try:
            # Resolve waypoints
            waypoints = (
                [params.get("source")]
                + params.get("intermediate_locations", [])
                + [params.get("destination")]
            )

            if len(waypoints) < 2:
                return {
                    "response_text": "At least source and destination are required.",
                    "actions": []
                }

            # Call the centralized Google route function
            result = await calculate_route_with_google(user_id, waypoints)

            route_type = "Multi-stop route" if params.get("intermediate_locations") else "Route"

            # optimal_routes is a list, pick the first for summary
            optimal_routes = result.get("optimal_routes")
            if not optimal_routes:
                return {
                    "response_text": result.get("message"),
                    "actions": []
                }
            
            # ✅ HARD SAFETY
            if not isinstance(optimal_routes, list) or len(optimal_routes) == 0:
                logger.error(f"[ROUTE DATA ERROR] No optimal_routes found: {result}")
                return {
                    "response_text": "No routes available.",
                    "actions": []
                }

            optimal_route = optimal_routes[0]
            distance = optimal_route.get("distance", "N/A")
            duration = optimal_route.get("duration", "N/A")

            return {
                "response_text": reply or f"{route_type} planned from {result['source']} → {result['destination']}. Distance: {distance}, ETA: {duration}",
                "actions": [{"type": "plan_route", "data": result}]
            }

        except Exception as e:
            logger.error(f"Error in _handle_plan_route: {e}", exc_info=True)
            return {"response_text": "Error planning route.", "actions": []}


    async def _handle_alternative_route(self, message, params, user_id, reply=None):
        """
        Handles alternative route calculation using Google API + Redis + DB.
        """
        route_id = params.get("route_id")
        reason = params.get("reason") or message or "Alternative route requested"
        source = params.get("source")
        destination = params.get("destination")
        intermediate_locations = params.get("intermediate_locations", [])

        if not route_id:
            return {"response_text": "Please provide a route_id.", "actions": []}

        try:
            # Build AlternativeRouteRequest object
            request_obj = AlternativeRouteRequest(
                route_id=route_id,
                reason=reason,
                source=source,
                destination=destination,
                intermediate_locations=intermediate_locations
            )

            # Call centralized alternative route function
            result = await get_alternative_function(request_obj, user_id)
            if not result.get("alternative_route"):
                return {
                "response_text": result.get("message"),
                "actions": []
            }

            return {
                "response_text": reply or f"Alternative route calculated for route {route_id}.",
                "actions": [
                    {
                        "type": "alternative_route",
                        "data": {
                            "alternative_route": result["alternative_route"],
                            "route_id": result["route_id"],
                            "parent_route_id": result["parent_route_id"],
                            "source": result["source"],
                            "destination": result["destination"],
                            "intermediate_locations": result["intermediate_locations"],
                            "waypoints": result.get("waypoints", []),
                            "reason": reason,
                            "route_cost": result.get("route_cost"),
                            "fuel_needed": result.get("fuel_needed"),
                            "is_alternative": True
                        }
                    }
                ]
            }

        except Exception as e:
            logger.error(f"Error in _handle_alternative_route: {e}", exc_info=True)
            return {"response_text": "Internal error calculating alternative route.", "actions": []}

    # async def _handle_assign_vehicle(self, message, params, user_id, reply=None):
    #     """
    #     Assigns an available vehicle matching the requested type(s) to a route.
    #     """
    #     try:
    #         source = params.get("source")
    #         destination = params.get("destination")
    #         intermediate_locations = params.get("intermediate_locations")
    #         # Normalize vehicle types
    #         vehicle_types_raw = params.get("vehicle_types", [])
    #         vehicle_types = []
    #         for vt in vehicle_types_raw:
    #             vehicle_types.extend([v.strip().lower() for v in vt.split()])  # split by space


    #         if not vehicle_types:
    #             return {"response_text": "No vehicle types specified for assignment.", "actions": []}

    #         # Find existing route
    #         route_id = await self._find_matching_route(source, destination, intermediate_locations, user_id)
    #         if not route_id:
    #             return {
    #                 "response_text": f"No route found from {source} to {destination}. Please create a route first.",
    #                 "actions": []
    #             }

    #         # Fetch available vehicles (sync DB call offloaded to executor)
    #         loop = asyncio.get_running_loop()
    #         available_vehicles = await loop.run_in_executor(None, get_available_vehicles_at_location, user_id, source)
            
    #         if not available_vehicles:
    #             return {"response_text": f"No available vehicles at {source}.", "actions": []}

    #         # Find matching vehicle
    #         target_vehicle = next(
    #             (v for v in available_vehicles
    #             if any(vt in v.get("type", "").lower() or vt in v.get("label", "").lower() 
    #                     for vt in vehicle_types)),
    #             None
    #         )

    #         logger.info(f"Available vehicles at {source}: {[v['type'] for v in available_vehicles]}")
    #         logger.info(f"Requested types: {vehicle_types}")
            
    #         if not target_vehicle:
    #             vehicle_type_str = ", ".join(vehicle_types)
    #             return {"response_text": f"No available {vehicle_type_str} at {source}.", "actions": []}
            
    #         logger.info(f"Vehicle: {target_vehicle}, {target_vehicle['id']}")
            
    #         # Prepare assignment request
    #         assignment_request = VehicleAssignmentRequest(
    #             vehicle_id=target_vehicle["id"],
    #             vehicle_type=target_vehicle.get("type", "truck"),
    #             route_id=route_id
    #         )

    #         # Assign vehicle
    #         result = await assign_vehicle_to_route_function(assignment_request, user_id)
    #         response_text = f"{reply}. (Route ID: {route_id}, Vehicle ID: {target_vehicle['id']})"

    #         return {
    #             "response_text": response_text or f"Assigned {target_vehicle.get('label', 'vehicle')} to route {route_id}.",
    #             "actions": [{"type": "assign_vehicles", "data": result}]
    #         }

    #     except Exception as e:
    #         logger.error(f"Error assigning vehicle: {e}", exc_info=True)
    #         return {"response_text": "Could not assign vehicle due to an internal error.", "actions": []}

    async def _handle_assign_vehicle(self, message, params, user_id, reply=None):
        """
        Assigns an available vehicle matching requested type(s) AND capacity
        to a matching route. Also computes arrival time using departure_time + route_duration.
        """
        try:
            source = params.get("source")
            destination = params.get("destination")
            intermediate_locations = params.get("intermediate_locations")

            #  REQUIRED CAPACITY
            required_capacity = params.get("capacity")
            if required_capacity is None:
                return {"response_text": "Please specify the required capacity.", "actions": []}

            #  VEHICLE TYPES NORMALIZATION
            vehicle_types_raw = params.get("vehicle_types", [])
            vehicle_types = []
            for vt in vehicle_types_raw:
                vehicle_types.extend([v.strip().lower() for v in vt.split()])

            if not vehicle_types:
                return {"response_text": "Please specify one or more vehicle types.", "actions": []}

            #  FIND ROUTE
            route_id = await self._find_matching_route(source, destination, intermediate_locations, user_id)
            if not route_id:
                return {
                    "response_text": f"No route found from {source} to {destination}. Please create a route first.",
                    "actions": []
                }

            #  CHECK AVAILABLE VEHICLES
            loop = asyncio.get_running_loop()
            available_vehicles = await loop.run_in_executor(
                None, get_available_vehicles_with_capacity, user_id, source, required_capacity
            )

            if not available_vehicles:
                return {"response_text": f"No available vehicles at {source}.", "actions": []}

            #  FILTER VEHICLE: match type & capacity
            target_vehicle = next(
                (
                    v for v in available_vehicles
                    if v.get("capacity", 0) >= required_capacity
                    and any(
                        vt in v.get("type", "").lower()
                        or vt in v.get("label", "").lower()
                        for vt in vehicle_types
                    )
                ),
                None
            )

            if not target_vehicle:
                return {
                    "response_text": (
                        f"No matching vehicle at {source} with type(s) {vehicle_types} "
                        f"and capacity >= {required_capacity}."
                    ),
                    "actions": []
                }

            logger.info(f"Selected Vehicle => {target_vehicle}")

            #  PREPARE ASSIGNMENT REQUEST
            assignment_request = VehicleAssignmentRequest(
                vehicle_id=target_vehicle["id"],
                vehicle_type=target_vehicle.get("type", "truck"),
                route_id=route_id,
                capacity=required_capacity
            )

            #  CALL ASSIGN FUNCTION
            result = await assign_vehicle_to_route_function(assignment_request, user_id)

            if not result.get("data"):
                return {
                    "response_text": result.get("message"),
                    "actions": []
                }


            #  CREATE REPLY TEXT
            response_text = f"{reply}. (Route ID: {route_id}, Vehicle ID: {target_vehicle['id']})"

            return {
                "response_text": response_text or f"Assigned {target_vehicle.get('label', 'vehicle')} to route {route_id}.",
                "actions": [
                    {
                        "type": "assign_vehicles",
                        "data": result
                    }
                ]
            }

        except Exception as e:
            logger.error(f"Error assigning vehicle: {e}", exc_info=True)
            return {"response_text": "Could not assign vehicle due to an internal error.", "actions": []}

   
    async def _handle_remove_route(self, message, params, user_id, reply=None):
        """
        Removes an existing route by:
        - route_id
        - source + destination
        - source + via + destination
        - route_data
        """

        try:
            # Normalize params
            if hasattr(params, "dict"):
                params = params.dict()

            if not isinstance(params, dict):
                return {
                    "response_text": "Invalid parameters for route removal.",
                    "actions": []
                }

            # Build RemoveRouteRequest
            remove_request = RemoveRouteRequest(
                route_id=params.get("route_id"),
                source=params.get("source"),
                destination=params.get("destination"),
                intermediate_locations=params.get("via") or params.get("intermediate_locations"),
                route_data=params.get("route_data")
            )

            # Call existing remove_route API internally
            result = await remove_route_function(remove_request, user_id)

            removed_id = result.get("route_id")

            if not removed_id:
                return {
                    "response_text": result.get("message"),
                    "actions": [],
                }
             
            return {
                "response_text": reply or f"Route {removed_id} removed successfully.",
                "actions": [{"type": "remove_route", "data": result}],
            }
        
        except Exception as e:
            logger.error(f"Error removing route: {e}", exc_info=True)
            return {
                "response_text": "An internal error occurred while removing the route.",
                "actions": []
            }


    # -------------------------
    # Reset single vehicle handler
    # -------------------------

    async def _handle_reset_single_vehicle(self, message, params, user_id, reply=None):
        """
        Resets a single vehicle to its original warehouse.
        Called for intent 'stop_vehicle'.
        """
        try:
            # -------------------- Validate params --------------------
            if not params or "vehicle_id" not in params:
                return {
                    "response_text": "Please provide a vehicle_id to reset.",
                    "actions": []
                }

            raw_vehicle_id = params["vehicle_id"]
            route_id = params.get("route_id")
            print(f"==>> route_id: {route_id}")

            # -------------------- Fetch user vehicles --------------------
            user_vehicles = get_vehicles_by_user(user_id)

            # -------------------- Resolve vehicle safely --------------------
            vehicle = None
            vehicle_id = None

            # Case 1: numeric string -> treat as ID
            if isinstance(raw_vehicle_id, str) and raw_vehicle_id.isdigit():
                vehicle_id = int(raw_vehicle_id)
                vehicle = next(
                    (v for v in user_vehicles if v.get("id") == vehicle_id),
                    None
                )

            # Case 2: integer ID
            elif isinstance(raw_vehicle_id, int):
                vehicle_id = raw_vehicle_id
                vehicle = next(
                    (v for v in user_vehicles if v.get("id") == vehicle_id),
                    None
                )

            # Case 3: non-numeric string -> treat as label
            elif isinstance(raw_vehicle_id, str):
                vehicle = next(
                    (v for v in user_vehicles if v.get("label", "").lower() == raw_vehicle_id.lower()),
                    None
                )
                if vehicle:
                    vehicle_id = vehicle["id"]

            # Vehicle not found
            if not vehicle:
                return {
                    "response_text": f"Vehicle '{raw_vehicle_id}' not found for user.",
                    "actions": []
                }

            vehicle_label = vehicle.get("label", f"Vehicle_{vehicle_id}")

            # -------------------- Prepare reset request --------------------
            vehicle_reset_request = ResetSingleVehicleRequest(
                vehicle_id=vehicle_id,
                route_id=route_id
            )
            print(f"==>> vehicle_reset_request: {vehicle_reset_request}")

            # -------------------- Call reset function --------------------
            result = await reset_single_vehicle_function(vehicle_reset_request, user_id)
            print(f"==>> result: {result}")


            
            # -------------------- Response --------------------
            response_text = reply or result.get(
                "message",
                f"Vehicle {vehicle_label} has been reset successfully."
            )

            return {
                "response_text": response_text,
                "actions": [{"type": "reset_vehicle", "data": result}]
            }

        except Exception as e:
            logger.error(
                f"Error resetting vehicle {params.get('vehicle_id')}: {e}",
                exc_info=True
            )
            return {
                "response_text": "An internal error occurred while resetting the vehicle.",
                "actions": []
            }

        

    async def _handle_clear_all_routes(self, message, params, user_id, reply=None):
        """
        Clears all routes and resets active vehicles for the user.
        """
        try:

            result = await clear_all_routes_function(user_id)            
            
            return {
                "response_text": reply or "All routes cleared and active vehicles reset successfully.",
                "actions": [{"type": "clear_map", "data": result}]
            }

        except Exception as e:
            logger.error(f"Error clearing all routes for user {user_id}: {e}", exc_info=True)
            return {
                "response_text": "Failed to clear all routes due to an internal error.",
                "actions": []
            }

# ---------------------
# Route helpers
# ---------------------

    async def _find_matching_route(self, source: str, destination: str, intermediate_locations: list, user_id: int) -> str:
        try:
            route = get_persistent_route_by_locations(
                user_id,
                source,
                destination,
                intermediate_locations
            )

            if not route:
                return None

            return route["route_id"]

        except Exception as e:
            logger.error(f"Error finding matching route: {e}", exc_info=True)
            return None

    

    async def _handle_clear_chat(self, message, params, user_id, reply=None):
        """
        Clears chat history for the given user.
        """
        try:
            await delete_data(user_id) 

            memory = get_chat_memory(user_id)
            memory.clear()
            logger.info(f"Chat history cleared for user_id={user_id}")

            return {
                "response_text": reply or "Chat history cleared successfully.",
                "actions": [{"type": "clear_chat"}]
            }
        except Exception as e:
            logger.error(f"Error clearing chat history for user_id={user_id}: {e}", exc_info=True)
            return {
                "response_text": "Failed to clear chat history due to an internal error.",
                "actions": []
            }

    async def _handle_satellite_view(self, message, params, user_id, reply=None):
        """
        Activates satellite view for the user.
        """
        try:
            # Here you can add any logic to switch the map view in your backend if needed
            logger.info(f"Satellite view activated for user_id={user_id}")

            return {
                "response_text": reply or "Satellite view activated.",
                "actions": [{"type": "satellite_view"}]
            }
        
        except Exception as e:
            logger.error(f"Error activating satellite view for user_id={user_id}: {e}", exc_info=True)
            return {
                "response_text": "Failed to activate satellite view.",
                "actions": []
            }

    async def _handle_street_view(self, message, params, user_id, reply=None):
        """
        Activates street view for the user.
        """
        try:
            # Here you can add any logic to switch the map view in your backend if needed
            logger.info(f"Street view activated for user_id={user_id}")

            return {
                "response_text": reply or "Street view activated.",
                "actions": [{"type": "street_view"}]
            }
        
        except Exception as e:
            logger.error(f"Error activating street view for user_id={user_id}: {e}", exc_info=True)
            return {
                "response_text": "Failed to activate street view.",
                "actions": []
            }
        
    async def _complete_vehicle_route(self, message, params, user_id, reply=None):
        """
        Marks a vehicle as having completed its assigned route.
        Intent: complete_vehicle_route
        """

        try:
            # Validate required parameters             
            route_id = params.get("route_id")
            vehicle_id = params.get("vehicle_id")
            destination = params.get("destination")

            if not route_id or not vehicle_id or not destination:
                return {
                    "response_text": "Please provide route_id, vehicle_id, and destination to complete the vehicle route.",
                    "actions": []
                }

            # Build the request object
            complete_request = VehicleCompleteRequest(
                route_id=route_id,
                vehicle_id=vehicle_id,
                destination=destination
            )

            # Call your existing backend function
            result = await complete_vehicle_route_function(complete_request, user_id)


            response_text = (
                reply or 
                result.get("message", f"Vehicle {vehicle_id} has completed route {route_id}.")
            )

            return {
                "response_text": response_text,
                "actions": [{"type": "complete_vehicle_route", "data": result}]
            }

        except Exception as e:
            logger.error(f"Error completing vehicle route: {e}", exc_info=True)
            return {
                "response_text": "An internal error occurred while completing the vehicle route.",
                "actions": []
            }


    async def _handle_help(self, message, params, user_id, reply=None):
        help_text = reply or (
            "I'm your route planning assistant. You can:\n"
            "• Plan optimal routes between locations\n"
            "• Assign vehicles to routes\n"
            "• Monitor vehicle movements in real-time\n"
            "• Get alternative routes for disruptions\n"
            "• Change Map View (Satellite view, Street view)\n"
            "• Clear Map with existing Routes and Vehicles\n"
            "• Clear Chat\n\n"
            "💡 Remember: Upload your CSV file first to enable route planning features!"
        )

        return {"response_text": help_text, "actions": []}

        
    #============================ multimodal ========================================

    async def _compute_multimodal_route(self, source: str, destination: str, user_id: int):
        """
        Internal wrapper for combined multimodal routing
        """
        try:
            payload = AirRouteRequest(
                source=source,
                destination=destination
            )

            result = await combined_route_function(payload, user_id)
            if not result.get("data"):
                return {"message": result.get("message")}
            
            return result

        except Exception as e:
            logger.error(f"Multimodal route failed: {e}", exc_info=True)
            return {"message": "Multimodal route calculation failed"}
        
    async def _handle_multimodal_route(self, message, params, user_id, reply=None):

        try:
            source = params.get("source")
            destination = params.get("destination")

            if not source or not destination:
                return {
                    "response_text": "Please provide both source and destination for multimodal routing.",
                    "actions": [],
                }

            result = await self._compute_multimodal_route(source, destination, user_id)

            if not result.get("data"):
                return {
                    "response_text": result.get("message"),
                    "actions": []
                }
            # if "status" not in result:
            #     result["status"] = True

            # if "data" not in result:
            #     # wrap whole result as data if misstructured
            #     result = {
            #         "status": True,
            #         "message": "Multimodal route served (normalized)",
            #         "data": result,
            #         "route_id": result.get("route_id"),
            #         "cached": result.get("cached", False),
            #         "source": source,
            #         "destination": destination
            #     }


            if not result.get("status"):
                return {
                    "response_text": "Multimodal route calculation failed.",
                    "actions": [],
                    "data": result
                }

            route_id = result.get("route_id")

            return {
                "response_text": reply or f"Multimodal route planned successfully from {source} → {destination}. (Route ID: {route_id})",
                "actions": [
                    {
                        "type": "multimodal_route",
                        "data": result
                    }
                ]
            }

        except Exception as e:
            logger.error(f"Error in multimodal handler: {e}", exc_info=True)
            return {
                "response_text": "Internal error while calculating multimodal route.",
                "actions": []
            }

    async def _remove_multimodal_route(self, params: dict, user_id: int):
        """
        Internal wrapper for removing multimodal routes
        """
        try:
            req = RemoveMultimodalRoute(
                route_id=params.get("route_id"),
                source=params.get("source"),
                destination=params.get("destination"),
                multimodal_data=params.get("multimodal_data")
            )

            result = await remove_multimodal_route_function(req, user_id)
            if not result.get("route_id"):
                return {"message": result.get("message")}
            
            return result

        except Exception as e:
            logger.error(f"Remove multimodal route failed: {e}", exc_info=True)
            return {"message": "Failed to remove multimodal route"}

        
    async def _handle_remove_multimodal_route(self, message, params, user_id, reply=None):

        try:
            if not params:
                return {
                    "response_text": "Please provide route_id or source & destination to remove a multimodal route.",
                    "actions": []
                }

            result = await self._remove_multimodal_route(params, user_id)
            route_id = result.get("route_id")            
            if not route_id:
                return {
                    "response_text": result.get("message"),
                    "actions": []
                }
                
            return {
                "response_text": reply or f"Multimodal route {route_id} removed successfully.",
                "actions": [
                    {
                        "type": "remove_multimodal_route",
                        "data": result
                    }
                ]
            }

        except Exception as e:
            logger.error(f"Error removing multimodal route: {e}", exc_info=True)
            return {
                "response_text": "Internal error while removing multimodal route.",
                "actions": []
            }

    async def _handle_reset_all_vehicles(self, message, params, user_id, reply=None):
        try:

            result = await reset_all_vehicles_function(user_id)
            if not result.get("vehicles_reset"):
                return {
                    "response_text": result.get("message"),
                    "actions": []
                }

            response_text = f"{reply}. Vehicles ID {result['vehicles_reset']})"

            return {
                "response_text": response_text or "Vehicles reset successfully.",
                "actions": [
                    {
                        "type": "reset_all_vehicles",
                        "data": result
                    }
                ]
            }

        except Exception as e:
            logger.error(f"Error reseting vehicles: {e}")
            return {
                "response_text": "Error reseting vehicles.",
                "actions": []
            }
        
    async def _handle_multimodal_assign_vehicle(self, message, params, user_id, reply=None):
        try:
            route_id = params.get("route_id")
            if not route_id:
                return {
                    "response_text": "Provide route ID.",
                    "actions": []
                }
                

            route = get_multimodal_route_by_id(user_id, route_id)
            if not route:
                return {
                    "response_text": "Route not found",
                    "actions": []
                }


            assigned_data = await assign_vehicle_multimodal(
                route=route,
                route_id=route_id,
                user_id=user_id
            )
            
            if not assigned_data.get("segment_1"):
                return {
                    "response_text": assigned_data.get("message"),
                    "actions": []
                }
            
            return {
                "response_text": reply or "Multimodal vehicles assigned successfully.",
                "actions": [
                    {
                        "type": "assign_vehicle_multimodal",
                        "route_id": route_id,
                        "data": assigned_data
                    }
                ]
            }

        except Exception as e:
            logger.error(f"Error assigning vehicle on multimodal route: {e}", exc_info=True)
            return {
                "response_text": "Internal error while assigning vehicle on multimodal route.",
                "actions": []
            }
        

    async def _handle_hub_to_capital_routes(self, message, params, user_id, reply=None):
        """
        Generates multimodal routes from hub to all capital nodes
        """
        try:
            result = await generate_hub_to_capital_routes(user_id)

            if not result.get("status"):
                return {
                    "response_text": "Failed to generate hub-to-capital routes.",
                    "actions": []
                }

            hub = result.get("hub")
            routes = result.get("routes", [])
            failures = result.get("failures", [])

            # -------------------------
            # RESPONSE
            # -------------------------
            success_count = len(routes)
            failure_count = len(failures)

            response_text = (
                reply
                or f"Generated {success_count} hub-to-capital multimodal routes from {hub}."
            )

            if failure_count:
                response_text += f" {failure_count} routes failed."

            return {
                "response_text": response_text,
                "actions": [
                    {
                        "type": "connect_hub",
                        "data": result
                    }
                ]
            }

        except Exception as e:
            logger.error(f"Hub-to-capital routing failed: {e}", exc_info=True)
            return {
                "response_text": "Internal error while generating hub-to-capital routes.",
                "actions": []
            }


    async def _handle_warehouse_status(self, message, params, user_id, reply=None):
        """
        Activates or deactivates a warehouse using warehouse_name
        Intent: activate_warehouse / deactivate_warehouse
        """
        try:
            warehouse_name = params.get("warehouse_name")
            print(f"==>> warehouse_name:  {warehouse_name}")
            action = params.get("is_active")  
            print(f"==>> action:  {action}")

            if not warehouse_name:
                return {
                    "response_text": "Please provide a warehouse name.",
                    "actions": []
                }

            # ---- Call your existing function ----
            result = await set_warehouse_active_status(
                user_id=user_id,
                warehouse_name=warehouse_name,
                is_active=action
            )

            if not result.get("data"):
               return {
                    "response_text": result.get("message"),
                    "actions": []
                }
            

            return {
                "response_text": reply or result["message"],
                "actions": [
                    {
                        "type": "warehouse_status_update",
                        "data": result
                    }
                ]
            }

        except Exception as e:
            logger.error("Warehouse status update failed", exc_info=True)
            return {
                "response_text": "Internal error while updating warehouse status.",
                "actions": []
            }
        
    async def _handle_fetch_routes(self, message, params, user_id, reply=None):
        """
        Fetches all routes for the current user.
        """
        from backend.routes.route_query import query_route_llm

        try:
            # Reuse existing logic to get user routes
            routes_data = await query_route_llm(message, user_id)

            if not routes_data.get("status"):
                return {
                    "response_text": routes_data.get("message"),    
                    "actions": []
                }
            
            print(f"==>> routes_data:-----========------------  {routes_data}")

            return {
                "response_text": routes_data.get("answer",""),
                
                "actions": [
                    {
                        "type": "fetch_routes",
                        "data": routes_data
                    }
                ]
            }

        except Exception as e:
            logger.error(f"Error fetching user routes: {e}", exc_info=True)
            return {
                "response_text": "Failed to fetch user routes due to an internal error.",
                "actions": []
            }

#================================= NEW ========================================================================================

    async def _handle_vehicle_status(self, message, params, user_id, reply=None):
        """
        Activates or deactivates a vehicle using vehicle_id
        Intent: activate_vehicle / deactivate_vehicle
        """
        try:
            vehicle_id = params.get("vehicle_id")
            print(f"==>> vehicle_id:  {vehicle_id}")
            action = params.get("is_active")  
            print(f"==>> action:  {action}")

            if not vehicle_id:
                return {
                    "response_text": "Please provide a vehicle ID.",
                    "actions": []
                }

            # ---- Call your existing function ----
            result = await set_vehicle_active_status(
                user_id=user_id,
                vehicle_id=vehicle_id,
                is_active=action
            )

            if not result.get("data"):
               return {
                    "response_text": result.get("message"),
                    "actions": []
                }
            

            return {
                "response_text": reply or result["message"],
                "actions": [
                    {
                        "type": "vehicle_status_update",
                        "data": result
                    }
                ]
            }

        except Exception as e:
            logger.error("Vehicle status update failed", exc_info=True)
            return {
                "response_text": "Internal error while updating vehicle status.",
                "actions": []
            }
        
    async def _handle_assign_plane(self, message, params, user_id, reply=None):
        """
        Explicitly assigns a PLANE to segment_2 of a multimodal route.
        Triggered by user intent: assign_plane
        """

        try:
            route_id = params.get("route_id")

            if not route_id:
                return {
                    "response_text": "Please provide a route ID to assign a plane.",
                    "actions": []
                }

            # ---- Fetch multimodal route ----
            route = get_multimodal_route_by_id(user_id, route_id)
            if not route:
                return {
                    "response_text": f"Multimodal route {route_id} not found.",
                    "actions": []
                }

            # ---- Assign only AIR segment ----
            from backend.routes.multimodalVehicle import assign_segment_2_air

            result = await assign_segment_2_air(
                route=route,
                route_id=route_id,
                user_id=user_id
            )

            if not result or result.get("message"):
                return {
                    "response_text": result.get("message", "No air segment found on this route."),
                    "actions": []
                }

            return {
                "response_text": (
                    reply
                    or f"Plane successfully assigned to route {route_id}."
                ),
                "actions": [
                    {
                        "type": "assign_plane",
                        "route_id": route_id,
                        "data": result
                    }
                ]
            }

        except Exception as e:
            logger.error(f"Error assigning plane for route {params.get('route_id')}: {e}", exc_info=True)
            return {
                "response_text": "Internal error while assigning plane.",
                "actions": []
            }



chat_service = ChatService()