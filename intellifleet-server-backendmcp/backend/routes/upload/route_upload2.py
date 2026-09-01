from pydantic import BaseModel
from typing import List, Optional
from fastapi import Depends, HTTPException, APIRouter
from fastapi.responses import JSONResponse
from fastapi import status
from backend.config.logger import logger
from backend.core.security import get_current_user
from backend.database.database import get_warehouse_by_name
from backend.routes.route_map.googleRoute import calculate_route_with_google
from backend.routes.route_map.testAIR import combined_route_function
from backend.routes.upload.route_upload import parse_intermediate
from backend.models.airRouteSchema import AirRouteRequest


class RouteItem(BaseModel):
    source: str
    destination: str
    intermediate: Optional[List[str]] = None
    type: str

class BulkRouteRequest(BaseModel):
    routes: List[RouteItem]


# async def upload_routes_json_function(user_id: int, payload: BulkRouteRequest):

#     inserted = 0
#     errors = []

#     road_routes = []
#     multimodal_routes = []
#     air_intermediate_route = []

#     # LOOP OVER EACH ROUTE
#     for idx, route in enumerate(payload.routes):

#         try:
#             src = route.source.strip()
#             dest = route.destination.strip()
#             mid = route.intermediate
#             route_type = route.type.strip().lower()

#             # Default objective handling
#             # objective = route.objective.strip() if route.objective else "duration"

#             # # Convert business words if needed
#             # if objective.lower() == "fastest":
#             #     objective = "duration"
#             # elif objective.lower() == "cheapest":
#             #     objective = "cost"

#             # if objective.lower() not in ["cost", "duration", "distance"]:
#             #     errors.append(
#             #         f"Route {idx+1}: Objective should be either cost, distance or duration"
#             #     )
#             #     continue

#             # Validate warehouses
#             src_warehouse = get_warehouse_by_name(user_id, src)
#             dest_warehouse = get_warehouse_by_name(user_id, dest)

#             if not src_warehouse or not dest_warehouse:
#                 errors.append(
#                     f"Route {idx+1}: Source or Destination warehouse not found"
#                 )
#                 continue

#             # Parse intermediate locations
#             mids = parse_intermediate(mid)

#             waypoints = [src]
#             if mids:
#                 waypoints.extend(mids)
#             waypoints.append(dest)

#             # ==================================
#             # ROAD ROUTE
#             # ==================================
#             if route_type in ("road", "land"):

#                 result = await calculate_route_with_google(
#                     user_id, waypoints, objective = "duration"
#                 )

#                 if not result.get("route_id"):
#                     errors.append(f"Route {idx+1}: Google route failed")
#                     continue

#                 road_routes.append(result)
#                 inserted += 1

#             # ==================================
#             # AIR ROUTE
#             # ==================================
#             elif route_type == "air":
#                 air_payload = AirRouteRequest(
#                     source=src,
#                     destination=dest,
#                     intermediate_locations=mids,
#                     objective="duration"
#                 )

#                 result = await combined_route_function(air_payload, user_id)

#                 # Force intermediate routes to air_intermediate
#                 if mids and len(mids) > 0:
#                     # Even if combined route returns route_id
#                     air_intermediate_route.append(result)
#                     inserted += 1
#                     continue

#                 if result.get("route_id"):
#                     multimodal_routes.append(result)
#                     inserted += 1

#                 elif result.get("routes"):
#                     air_intermediate_route.append(result)
#                     inserted += 1

#                 else:
#                     errors.append(f"Route {idx+1}: Route failed")


#             else:
#                 errors.append(
#                     f"Route {idx+1}: Invalid RouteType '{route_type}'"
#                 )
#                 continue

#         except Exception as e:
#             logger.error(f"Error processing route {idx+1}: {e}")
#             errors.append(f"Route {idx+1}: {str(e)}")

#     # FINAL RESPONSE (same structure as CSV API)
#     return {
#         "success": True,
#         "message": f"Successfully uploaded {inserted} routes.",
#         "data": {
#             "road_routes": road_routes,
#             "multimodal_routes": multimodal_routes,
#             "air_intermediate_route": air_intermediate_route
#         },
#         "errors": errors
#     }


async def upload_routes_json_function(user_id: int, payload: BulkRouteRequest):

    inserted = 0
    errors = []

    road_routes = []
    multimodal_routes = []
    air_intermediate_route = []

    for idx, route in enumerate(payload.routes):

        try:
            src = route.source.strip()
            dest = route.destination.strip()
            mid = route.intermediate
            route_type = route.type.strip().lower()

            # ===============================
            # VALIDATE SOURCE & DESTINATION
            # ===============================
            src_warehouse = get_warehouse_by_name(user_id, src)
            dest_warehouse = get_warehouse_by_name(user_id, dest)

            error_parts = []

            if not src_warehouse:
                error_parts.append(f"Source '{src}' not found")

            if not dest_warehouse:
                error_parts.append(f"Destination '{dest}' not found")

            # Parse intermediate locations
            # mids = parse_intermediate(mid)

            # Parse intermediate locations safely
            try:
                mids = parse_intermediate(mid) if mid else []
            except Exception:
                mids = []

            if mids is None:
                mids = []
            # ===============================
            # VALIDATE INTERMEDIATES
            # ===============================
            invalid_intermediates = []
            for m in mids:
                wh = get_warehouse_by_name(user_id, m)
                if not wh:
                    invalid_intermediates.append(m)

            if invalid_intermediates:
                error_parts.append(
                    f"Intermediate warehouse(s) not found: {', '.join(invalid_intermediates)}"
                )

            # If any warehouse errors → skip this route
            if error_parts:
                errors.append(
                    f"Route {idx+1}: " + " | ".join(error_parts)
                )
                continue

            # ===============================
            # BUILD WAYPOINTS
            # ===============================
            waypoints = [src]
            if mids:
                waypoints.extend(mids)
            waypoints.append(dest)

            # ===============================
            # ROAD ROUTE
            # ===============================
            if route_type in ("road", "land"):

                result = await calculate_route_with_google(
                    user_id, waypoints, objective="duration"
                )

                if not result.get("route_id"):
                    errors.append(
                        f"Route {idx+1}: Road route creation failed"
                    )
                    continue

                road_routes.append(result)
                inserted += 1

            # ===============================
            # AIR ROUTE
            # ===============================
            elif route_type == "air":

                air_payload = AirRouteRequest(
                    source=src,
                    destination=dest,
                    intermediate_locations=mids,
                    objective="duration"
                )

                result = await combined_route_function(
                    air_payload, user_id
                )

                if mids and len(mids) > 0:
                    air_intermediate_route.append(result)
                    inserted += 1
                    continue

                if result.get("route_id"):
                    multimodal_routes.append(result)
                    inserted += 1

                elif result.get("routes"):
                    air_intermediate_route.append(result)
                    inserted += 1

                else:
                    errors.append(
                        f"Route {idx+1}: Air route creation failed"
                    )

            # ===============================
            # INVALID ROUTE TYPE
            # ===============================
            else:
                errors.append(
                    f"Route {idx+1}: Invalid RouteType '{route_type}'"
                )
                continue

        except Exception as e:
            logger.error(f"Error processing route {idx+1}: {e}")
            errors.append(
                f"Route {idx+1}: Unexpected error - {str(e)}"
            )

    # ======================================
    # FINAL MESSAGE BUILDING
    # ======================================
    failed_count = len(errors)

    if failed_count > 0:
        final_message = (
            f"Successfully uploaded {inserted} route(s). "
            f"{failed_count} route(s) failed. "
            f"Issues: " + " || ".join(errors)
        )
    else:
        final_message = (
            f"Successfully uploaded {inserted} route(s)."
        )

    return {
        "success": True,
        "message": final_message,
        "data": {
            "road_routes": road_routes,
            "multimodal_routes": multimodal_routes,
            "air_intermediate_route": air_intermediate_route
        },
        "errors": errors
    }

router = APIRouter(tags=["Upload Routes JSON"])

@router.post("/upload-routes-json")
async def upload_routes_json(
    payload: BulkRouteRequest,
    current_user: int = Depends(get_current_user)
):

    try:

        user_id = current_user.get("user_id")

        if not user_id:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "Invalid token: user_id not found"
                }
            )

        result = await upload_routes_json_function(user_id, payload)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                    "upload_type": "route",
                    **result
            }
        )

    except Exception as e:
        logger.error(f"Unexpected error in upload_routes_json: {str(e)}")

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": "Internal server error",
            }
        )
