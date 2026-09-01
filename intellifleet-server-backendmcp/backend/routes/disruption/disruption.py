# """
# Disruption Management API
# Handles route disruptions and finds alternative warehouse fulfillment options.

# All data (warehouses, routes, vehicles) is loaded from the DB internally using
# user_id — callers never need to pass DataFrames or edges dicts.
# """

# import logging

# from fastapi import APIRouter, HTTPException
# from pydantic import BaseModel
# from typing import Optional
# from backend.routes.disruption.utils import *
# import numpy as np

# # from disruption_manager import DisruptionManager, analyze_disruption_scenario
# # from disruption_db import prepare_disruption_data

# logger = logging.getLogger(__name__)

# disruption_router = APIRouter(prefix="/disruption", tags=["disruption"])


# # ─────────────────────────────────────────────────────────────────────────────
# # REQUEST MODEL
# # ─────────────────────────────────────────────────────────────────────────────

# class UnifiedDisruptionRequest(BaseModel):

#     # ── Required for all operations ───────────────────────────────────────────
#     operation: str

#     # ── handle_disruption fields ──────────────────────────────────────────────
#     source_warehouse:       Optional[str]   = None
#     destination_city:       Optional[str]   = None
#     demand_kg:              Optional[float] = None
#     repair_hours:           Optional[int]   = None
#     disruption_location:    Optional[str]   = None

#     # ── find_warehouses fields ────────────────────────────────────────────────
#     origin_lat:     Optional[float] = None
#     origin_lon:     Optional[float] = None
#     demand_weight:  Optional[int]   = None
#     exclude_cities: Optional[list]  = None
#     max_results:    Optional[int]   = None

#     # ── estimate_delivery fields ──────────────────────────────────────────────
#     source_city:           Optional[str] = None
#     repair_duration_hours: Optional[int] = None

#     # ── shared ────────────────────────────────────────────────────────────────
#     disruption_time:        Optional[str] = None
#     required_delivery_time: Optional[str] = None


# # ─────────────────────────────────────────────────────────────────────────────
# # HELPERS
# # ─────────────────────────────────────────────────────────────────────────────

# def _require(fields: dict, operation: str) -> None:
#     """Raise 400 if any field in *fields* is None."""
#     missing = [name for name, val in fields.items() if val is None]
#     if missing:
#         raise HTTPException(
#             status_code=400,
#             detail=(
#                 f"Missing required fields for {operation}: "
#                 f"{', '.join(missing)}"
#             ),
#         )


# def _convert(obj):
#     """Recursively convert numpy / non-JSON-serialisable types."""
    
#     if isinstance(obj, dict):
#         return {k: _convert(v) for k, v in obj.items()}

#     if isinstance(obj, list):
#         return [_convert(v) for v in obj]

#     # ✅ Handle numpy types
#     if isinstance(obj, (np.integer,)):
#         return int(obj)

#     if isinstance(obj, (np.floating,)):
#         val = float(obj)
#         if math.isinf(val) or math.isnan(val):
#             return None
#         return val

#     if isinstance(obj, (np.bool_,)):
#         return bool(obj)

#     # ✅ Handle Python float edge cases (THIS IS YOUR BUG FIX)
#     if isinstance(obj, float):
#         if math.isinf(obj) or math.isnan(obj):
#             return None

#     return obj

# async def manage_disruption(request: UnifiedDisruptionRequest, user_id: int):
#     try:
#         # ── OPERATION: handle_disruption ──────────────────────────────────────
#         if request.operation == "handle_disruption":
#             _require({
#                 "source_warehouse":       request.source_warehouse,
#                 "destination_city":       request.destination_city,
#                 "demand_kg":              request.demand_kg,
#                 "disruption_time":        request.disruption_time,
#                 "required_delivery_time": request.required_delivery_time,
#                 "repair_hours":           request.repair_hours,
#             }, "handle_disruption")

#             result = await analyze_disruption_scenario(
#                 user_id=user_id,
#                 source_warehouse=request.source_warehouse,
#                 destination_city=request.destination_city,
#                 demand_weight=int(request.demand_kg),
#                 disruption_time=request.disruption_time,
#                 required_delivery_time=request.required_delivery_time,
#                 repair_duration_hours=request.repair_hours,
#                 disruption_location=request.disruption_location,
#             )

#             logger.info(
#                 f"[DISRUPTION] handle_disruption | user={user_id} | "
#                 f"{request.source_warehouse} → {request.destination_city} | "
#                 f"demand={request.demand_kg}kg"
#             )

#             return _convert(result)

#         # ── OPERATION: find_warehouses ────────────────────────────────────────
#         elif request.operation == "find_warehouses":
#             _require({
#                 "origin_lat":    request.origin_lat,
#                 "origin_lon":    request.origin_lon,
#                 "demand_weight": request.demand_weight,
#             }, "find_warehouses")

#             manager = DisruptionManager(user_id=user_id)

#             result = manager.find_nearest_warehouses(
#                 origin_lat=request.origin_lat,
#                 origin_lon=request.origin_lon,
#                 demand_weight=request.demand_weight,
#                 exclude_cities=request.exclude_cities,
#                 max_results=request.max_results,
#             )

#             logger.info(
#                 f"[DISRUPTION] find_warehouses | user={user_id} | "
#                 f"origin=({request.origin_lat}, {request.origin_lon}) | "
#                 f"demand={request.demand_weight}kg"
#             )

#             return _convert(result)

#         # ── OPERATION: estimate_delivery ──────────────────────────────────────
#         elif request.operation == "estimate_delivery":
#             _require({
#                 "source_city":            request.source_city,
#                 "destination_city":       request.destination_city,
#                 "repair_duration_hours":  request.repair_duration_hours,
#                 "disruption_time":        request.disruption_time,
#                 "required_delivery_time": request.required_delivery_time,
#             }, "estimate_delivery")

#             manager = DisruptionManager(user_id=user_id)

#             result = manager.estimate_delivery_time(
#                 source_city=request.source_city,
#                 destination_city=request.destination_city,
#                 repair_duration_hours=request.repair_duration_hours,
#                 disruption_time=request.disruption_time,
#                 required_delivery_time=request.required_delivery_time,
#             )

#             logger.info(
#                 f"[DISRUPTION] estimate_delivery | user={user_id} | "
#                 f"{request.source_city} → {request.destination_city}"
#             )

#             return _convert(result)

#     except Exception as exc:
#         logger.error(
#             f"[DISRUPTION] Unhandled error | operation='{request.operation}' | "
#             f"user={user_id} | {exc}",
#             exc_info=True,
#         )
#         return {"message": f"Operation failed!"}



# ========== FIXED process_disruption function ==========

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Union
import logging
import numpy as np
import pandas as pd
from backend.config.config import settings
from backend.database.database import prepare_disruption_data, get_nodes_by_user
from backend.routes.disruption.utils import convert_numpy_types, DisruptionManager

from backend.core.security import get_current_user

logger = logging.getLogger(__name__)
disruption_router = APIRouter(prefix="/disruption", tags=["disruption"])


from typing import Union
import re 

def parse_delay_duration(delay_input: Union[str, int]) -> int:

    # If already an integer, assume it's in minutes
    if isinstance(delay_input, int):
        return delay_input
    
    if not isinstance(delay_input, str):
        raise ValueError(f"Delay must be string or integer, got {type(delay_input)}")
    
    delay_str = delay_input.strip().lower()
    total_minutes = 0
    
    # Handle special phrases
    if 'half hour' in delay_str or 'half-hour' in delay_str:
        total_minutes += 30
        delay_str = delay_str.replace('half hour', '').replace('half-hour', '')
    
    if 'quarter hour' in delay_str or 'quarter-hour' in delay_str:
        total_minutes += 15
        delay_str = delay_str.replace('quarter hour', '').replace('quarter-hour', '')
    
    # Extract hours
    hours_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)(?:\s|$)', delay_str)
    if hours_match:
        hours = float(hours_match.group(1))
        total_minutes += int(hours * 60)
        delay_str = delay_str.replace(hours_match.group(0), '')
    
    # Extract minutes
    minutes_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m)(?:\s|$)', delay_str)
    if minutes_match:
        minutes = float(minutes_match.group(1))
        total_minutes += int(minutes)
        delay_str = delay_str.replace(minutes_match.group(0), '')
    
    # If no matches found, raise error
    if total_minutes == 0 and delay_str.strip():
        raise ValueError(
            f"Could not parse delay: '{delay_input}'. "
            f"Supported formats: '7 hours', '30 minutes', '2 hours 30 minutes', '420' (minutes as int)"
        )
    
    if total_minutes == 0:
        raise ValueError(f"Delay value must be greater than 0")
    
    return total_minutes

class UnifiedDisruptionRequest(BaseModel):

    route_type: str
    source_warehouse: Optional[str] = None
    destination_city: Optional[str] = None
    demand_kg: Optional[float] = None
    disruption_time: Optional[str] = None          
    required_delivery_time: Optional[str] = None   

    repair_hours: Optional[Union[str, int]] = None   
    disruption_location: Optional[str] = None

    flight_delay_minutes: Optional[Union[str, int]] = None
 
@disruption_router.post("/manage")
async def manage_disruption(request: UnifiedDisruptionRequest, current_user: dict = Depends(get_current_user)):

    user_id = current_user.get("user_id")
    # warehouses_df, road_routes_df, vehicles_df, air_routes_df = prepare_disruption_data(user_id)

    # rows     = get_nodes_by_user(user_id)

    # nodes_df = pd.DataFrame(rows) if rows else pd.DataFrame(
    #     columns=["route_id", "from_location", "to_location",
    #             "distance", "duration", "cost", "route_type"]
    # )

    # if warehouses_df is None or warehouses_df.empty:
    #     return {
    #         "message": "No warehouses found for this user. Please add warehouses to manage disruptions."
    #     }
    
    # if road_routes_df is None or road_routes_df.empty:
    #     return {
    #         "message": "No road routes found for this user. Please add road routes to manage disruptions."
    #     }
        
    # if vehicles_df is None or vehicles_df.empty:
    #     return {
    #         "message": "No vehicles found for this user. Please add vehicles to manage disruptions."
    #     }
    
    # if air_routes_df is None or air_routes_df.empty:
    #     return {
    #         "message": "No air routes found for this user. Please add air routes to manage disruptions."
    #     }


    try:

        google_api_key = settings.GOOGLE_MAPS_API_KEY

        manager = DisruptionManager(
            user_id=user_id,
            # warehouses_df=warehouses_df,
            # road_routes_df=road_routes_df,
            # vehicles_df=vehicles_df,
            # air_routes_df=air_routes_df,
            # nodes_df=nodes_df,
            google_api_key=google_api_key
        )

        if request.route_type == "air":

            parsed_delay_minutes = parse_delay_duration(request.flight_delay_minutes)

            result = manager.handle_air_route_disruption(
                source_warehouse=request.source_warehouse,
                destination_city=request.destination_city,
                demand_weight=int(request.demand_kg),
                disruption_time=request.disruption_time,
                flight_delay_minutes=parsed_delay_minutes,
                required_delivery_time=request.required_delivery_time,
            )

            logger.info(
                f"✅ Handled air disruption: {request.source_warehouse} → "
                f"{request.destination_city} (delay: {parsed_delay_minutes} min)"
            )

        elif request.route_type == "road":

            if isinstance(request.repair_hours, (int, float)):
                parsed_repair_hours = request.repair_hours
            else:
                parsed_repair_hours = parse_delay_duration(request.repair_hours) / 60

            result = manager.handle_road_disruption(
                source_warehouse=request.source_warehouse,
                destination_city=request.destination_city,
                demand_weight=int(request.demand_kg),
                disruption_time=request.disruption_time,
                repair_hours=int(parsed_repair_hours),
                required_delivery_time=request.required_delivery_time,
                disruption_location=request.disruption_location,
            )

            logger.info(
                f"✅ Handled road disruption: {request.source_warehouse} → "
                f"{request.destination_city} (repair: {parsed_repair_hours:.1f} h)"
            )

        if 'formatted_output' in result:
            print(result['formatted_output'])

        return convert_numpy_types(result)

    except Exception as e:
        logger.error(f"Disruption management error: {e}", exc_info=True)
        return {"message": "Failed to manage disruption!"}
    

async def manage_disruption_function(request: UnifiedDisruptionRequest, user_id: int):

    # warehouses_df, road_routes_df, vehicles_df, air_routes_df = prepare_disruption_data(user_id)

    # rows     = get_nodes_by_user(user_id)

    # nodes_df = pd.DataFrame(rows) if rows else pd.DataFrame(
    #     columns=["route_id", "from_location", "to_location",
    #             "distance", "duration", "cost", "route_type"]
    # )

    # if warehouses_df is None or warehouses_df.empty:
    #     return {
    #         "message": "No warehouses found for this user. Please add warehouses to manage disruptions."
    #     }
    
    # if road_routes_df is None or road_routes_df.empty:
    #     return {
    #         "message": "No road routes found for this user. Please add road routes to manage disruptions."
    #     }
        
    # if vehicles_df is None or vehicles_df.empty:
    #     return {
    #         "message": "No vehicles found for this user. Please add vehicles to manage disruptions."
    #     }
    
    # if air_routes_df is None or air_routes_df.empty:
    #     return {
    #         "message": "No air routes found for this user. Please add air routes to manage disruptions."
    #     }


    try:

        google_api_key = settings.GOOGLE_MAPS_API_KEY

        manager = DisruptionManager(
            user_id=user_id,
            # warehouses_df=warehouses_df,
            # road_routes_df=road_routes_df,
            # vehicles_df=vehicles_df,
            # air_routes_df=air_routes_df,
            # nodes_df=nodes_df,
            google_api_key=google_api_key
        )

        if request.route_type == "air":

            parsed_delay_minutes = parse_delay_duration(request.flight_delay_minutes)

            result = manager.handle_air_route_disruption(
                source_warehouse=request.source_warehouse,
                destination_city=request.destination_city,
                demand_weight=int(request.demand_kg),
                disruption_time=request.disruption_time,
                flight_delay_minutes=parsed_delay_minutes,
                required_delivery_time=request.required_delivery_time,
            )

            logger.info(
                f"✅ Handled air disruption: {request.source_warehouse} → "
                f"{request.destination_city} (delay: {parsed_delay_minutes} min)"
            )

        elif request.route_type == "road":

            if isinstance(request.repair_hours, (int, float)):
                parsed_repair_hours = request.repair_hours
            else:
                parsed_repair_hours = parse_delay_duration(request.repair_hours) / 60

            result = manager.handle_road_disruption(
                source_warehouse=request.source_warehouse,
                destination_city=request.destination_city,
                demand_weight=int(request.demand_kg),
                disruption_time=request.disruption_time,
                repair_hours=int(parsed_repair_hours),
                required_delivery_time=request.required_delivery_time,
                disruption_location=request.disruption_location,
            )

            logger.info(
                f"✅ Handled road disruption: {request.source_warehouse} → "
                f"{request.destination_city} (repair: {parsed_repair_hours:.1f} h)"
            )

        if 'formatted_output' in result:
            print(result['formatted_output'])

        return convert_numpy_types(result)

    except Exception as e:
        logger.error(f"Disruption management error: {e}", exc_info=True)
        return {"message": "Failed to manage disruption!"}