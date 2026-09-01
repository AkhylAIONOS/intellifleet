from ..database.database import get_warehouse_by_name
from fastapi import HTTPException
from typing import List
from ..models.routeSchema import GoogleRouteRequest
from ..config.config import settings
import polyline
import httpx
from .optimizer import *
from ..config.logger import logger


GOOGLE_MAPS_API_KEY = settings.GOOGLE_MAPS_API_KEY

ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"
GOOGLE_DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

def fetch_warehouse_addresses(user_id: int, waypoints: List[str]):
    addresses = []

    for name in waypoints:
        wh = get_warehouse_by_name(user_id, name)

        if not wh:
            return {
                "message": f"Warehouse '{name}' not found in your account. Please check the name or upload the warehouse before using it in routes."
            }
        
        if wh:
            if not wh.get("is_active"):
                return {
                    "message": f"Warehouse '{name}' is inactive. Please activate it to use in routes."
                }

            address = wh.get("address")
            if not address:
                return {
                    "message": f"Warehouse '{name}' does not have an address. Please update the warehouse with a valid address to use in routes."
                }

            addresses.append(address)

        else:
            addresses.append(name)

    return addresses

# async def compute_route_for_user(payload: GoogleRouteRequest, user_id: int):
    
#     source = payload.source
#     destination = payload.destination
#     intermediate_locations = payload.intermediate_locations

#     try:
#         if not intermediate_locations:
#             if not source or not destination:
#                 return {"error": "Source and Destination are required"}
    
#         intermediates_list = []

#         if intermediate_locations:
#             for i in intermediate_locations:
#                 intermediates_list.append({
#                     "address": i
#                 })


#         body = {
#             "origin": {
#                 "address": source
#             },
#             "destination": {
#                 "address": destination
#             },
#             "intermediates": intermediates_list,
#             "travelMode": "DRIVE",
#             "computeAlternativeRoutes": True,
#             "polylineQuality": "HIGH_QUALITY",
#             "polylineEncoding": "ENCODED_POLYLINE"
#         }

#         FIELD_MASK = (
#             "routes.distanceMeters,"
#             "routes.duration,"
#             "routes.polyline.encodedPolyline"
#         )

#         headers = {
#             "Content-Type": "application/json",
#             "X-Goog-FieldMask": FIELD_MASK,
#             "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY
#         }

#         async with httpx.AsyncClient(timeout=20.0) as client:
#             response = await client.post(
#                 ROUTES_ENDPOINT,
#                 headers=headers,
#                 json=body
#             )

#         if response.status_code != 200:
#             return {
#                 "error": "Google API error",
#                 "status": response.status_code,
#                 "details": response.text
#             }

#         data = response.json()
        
#         routes = []
#         for r in data.get("routes", []):
#             encoded = r.get("polyline", {}).get("encodedPolyline")
#             distance = r.get("distanceMeters", 0) / 1000
#             duration = convertDuration(r.get("duration"))
            
#             decoded_path = polyline.decode(encoded)
#             decoded_path_dicts = [{"lat": lat, "lng": lng} for lat, lng in decoded_path]

#             routes.append({
#                 "distance": distance,
#                 "duration": duration,    
#                 "path": decoded_path_dicts     
#             })

#         result = {
#             "source": source,
#             "destination": destination,
#             "intermediate_locations": intermediate_locations,
#             "routes": routes
#         }

#         return {
#             "status": True,
#             "message": "Routes Calculated",
#             "data": result
            
#         }
    
#     except Exception as e:
#         return {
#             "status": False,
#             "message": "Computing route failed.",
#             "error": str(e)
#         }


# async def compute_route_for_user(payload: GoogleRouteRequest, user_id: int):
#     source = payload.source
#     destination = payload.destination
#     intermediate_locations = payload.intermediate_locations
#     objective = payload.objective

#     try:
#         if not intermediate_locations:
#             if not source or not destination:
#                 return {"error": "Source and Destination are required"}
    
#         intermediates_list = []
#         if intermediate_locations:
#             for i in intermediate_locations:
#                 intermediates_list.append({"address": i})

#         body = {
#             "origin": {"address": source},
#             "destination": {"address": destination},
#             "intermediates": intermediates_list,
#             "travelMode": "DRIVE",
#             "computeAlternativeRoutes": True,
#             "polylineQuality": "HIGH_QUALITY",
#             "polylineEncoding": "ENCODED_POLYLINE"
#         }

#         FIELD_MASK = (
#             "routes.distanceMeters,"
#             "routes.duration,"
#             "routes.polyline.encodedPolyline"
#         )

#         headers = {
#             "Content-Type": "application/json",
#             "X-Goog-FieldMask": FIELD_MASK,
#             "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY
#         }

#         async with httpx.AsyncClient(timeout=20.0) as client:
#             response = await client.post(ROUTES_ENDPOINT, headers=headers, json=body)

#         if response.status_code != 200:
#             return {
#                 "error": "Google API error",
#                 "status": response.status_code,
#                 "details": response.text
#             }

#         data = response.json()
        
#         routes = []
#         for r in data.get("routes", []):
#             encoded = r.get("polyline", {}).get("encodedPolyline")
#             distance_km = r.get("distanceMeters", 0) / 1000
#             duration_hr = convertDuration(r.get("duration"))

#             decoded_path = polyline.decode(encoded)
#             decoded_path_dicts = [{"lat": lat, "lng": lng} for lat, lng in decoded_path]

#             # cost = 5 INR per km (adjust per vehicle/fuel type)
#             fuel_cost = distance_km * 15  

#             routes.append({
#                 "distance": distance_km,
#                 "duration": duration_hr,
#                 "cost": fuel_cost,
#                 "path": decoded_path_dicts
#             })

#         # -----------------------------
#         # Optimization Logic
#         # -----------------------------
#         if not routes:
#             return {"error": "No routes returned"}

#         if objective in ["costliest"]:
#             best_route = max(routes, key=lambda r: r["cost"])
#         elif objective in ["longest"]:
#             best_route = max(routes, key=lambda r: r["distance"])
#         elif objective in ["slowest"]:
#             best_route = max(routes, key=lambda r: r["duration"])
#         elif objective in ["fastest"]:
#             best_route = min(routes, key=lambda r: r["duration"])
#         elif objective in ["shortest"]:
#             best_route = min(routes, key=lambda r: r["distance"])
#         elif objective in ["cheapest"]:
#             best_route = min(routes, key=lambda r: r["cost"])
#         else:
#             best_route = min(routes, key=lambda r: r["duration"])

#         result = {
#             "source": source,
#             "destination": destination,
#             "intermediate_locations": intermediate_locations,
#             "objective_used": objective,
#             "routes": routes,
#             "best_route": best_route
#         }

#         return {
#             "status": True,
#             "message": "Routes Calculated & Optimized",
#             "data": result
#         }

#     except Exception as e:
#         return {
#             "status": False,
#             "message": "Computing route failed.",
#             "error": str(e)
#         }


# async def compute_route_for_user(payload: GoogleRouteRequest, user_id: int):

#     source = payload.source
#     destination = payload.destination
#     intermediate_locations = payload.intermediate_locations
#     objective = payload.objective

#     try:
#         if not source or not destination:
#             return {"message": "Source and Destination are required"}

#         intermediates_list = []
#         if intermediate_locations:
#             intermediates_list = [{"address": i} for i in intermediate_locations]

#         body = {
#             "origin": {"address": source},
#             "destination": {"address": destination},
#             "intermediates": intermediates_list,
#             "travelMode": "DRIVE",
#             "computeAlternativeRoutes": True,
#             "polylineQuality": "HIGH_QUALITY",
#             "polylineEncoding": "ENCODED_POLYLINE"
#         }

#         FIELD_MASK = (
#             "routes.distanceMeters,"
#             "routes.duration,"
#             "routes.polyline.encodedPolyline"
#         )

#         headers = {
#             "Content-Type": "application/json",
#             "X-Goog-FieldMask": FIELD_MASK,
#             "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY
#         }

#         async with httpx.AsyncClient(timeout=20.0) as client:
#             response = await client.post(
#                 ROUTES_ENDPOINT,
#                 headers=headers,
#                 json=body
#             )

#         if response.status_code != 200:
#             logger.error(f"Google API error: {response.text}")
#             return {
#                 "message": "Google API error",
#             }

#         data = response.json()
#         google_routes = data.get("routes", [])

#         if not google_routes:
#             return {"message": "No routes returned"}

#         # -------------------------------------------------
#         # BUILD ROUTE OBJECTS (FOR COMPARISON)
#         # -------------------------------------------------

#         all_routes = []
#         nodes = {"START": source, "END": destination}
#         edges = {}

#         for idx, r in enumerate(google_routes):
#             route_node = f"R{idx}"
#             nodes[route_node] = route_node

#             distance_km = r.get("distanceMeters", 0) / 1000
#             duration_hr = convertDuration(r.get("duration"))

#             encoded = r.get("polyline", {}).get("encodedPolyline")
#             decoded_path = polyline.decode(encoded)
#             decoded_path_dicts = [{"lat": lat, "lng": lng} for lat, lng in decoded_path]

#             route_data = {
#                 "distance": round(distance_km, 2),
#                 "duration": round(duration_hr, 2),
#                 "path": decoded_path_dicts
#             }

#             all_routes.append(route_data)

#             # START → Ri
#             edges[("START", route_node)] = {
#                 "from": "START",
#                 "to": route_node,
#                 "distance": distance_km,
#                 "time": duration_hr,
#                 "fuel": distance_km,
#                 "path": decoded_path_dicts,
#             }

#             # Ri → END
#             edges[(route_node, "END")] = {
#                 "from": route_node,
#                 "to": "END",
#                 "distance": 0,
#                 "time": 0,
#                 "fuel": 0
#             }

#         # -------------------------------------------------
#         # OPTIMIZATION
#         # -------------------------------------------------

#         best_edges = await optimize(
#             nodes=nodes,
#             edges=edges,
#             start="START",
#             end="END",
#             objective=objective 
#         )

#         if not best_edges:
#             return {"message": "No optimal route found"}

#         best_route_edge = next(e for e in best_edges if "path" in e)

#         best_route = {
#             "distance": round(best_route_edge["distance"], 2),
#             "duration": round(best_route_edge["time"], 2),
#             "path": best_route_edge["path"]
#         }

#         return {
#             "message": "Routes calculated successfully",
#             "data": {
#                 "source": source,
#                 "destination": destination,
#                 "intermediate_locations": intermediate_locations,
#                 "best_route": best_route,
#                 "routes": all_routes
#             }
#         }

#     except Exception as e:
#         logger.error(f"Error in compute_route_for_user: {e}")
#         return {
#             "message": "Computing route failed",
#         }
    
    
async def compute_route_for_user(payload: GoogleRouteRequest, user_id: int):
    source = payload.source
    destination = payload.destination
    intermediate_locations = payload.intermediate_locations
    objective = payload.objective

    logger.info(f"[ROUTE REQUEST] User={user_id}, Source={source}, Destination={destination}, Intermediates={intermediate_locations}, Objective={objective}")

    try:
        if not source or not destination:
            logger.warning("[ROUTE ERROR] Missing source or destination")
            return {"message": "Source and Destination are required"}

        intermediates_list = []
        if intermediate_locations:
            intermediates_list = [{"address": i} for i in intermediate_locations]

        body = {
            "origin": {"address": source},
            "destination": {"address": destination},
            "intermediates": intermediates_list,
            "travelMode": "DRIVE",
            "computeAlternativeRoutes": True,
            "polylineQuality": "HIGH_QUALITY",
            "polylineEncoding": "ENCODED_POLYLINE"
        }

        FIELD_MASK = ("routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline")
        headers = {
            "Content-Type": "application/json",
            "X-Goog-FieldMask": FIELD_MASK,
            "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(ROUTES_ENDPOINT, headers=headers, json=body)

        if response.status_code != 200:
            logger.error(f"[GOOGLE API ERROR] Status={response.status_code}")
            return {"message": "Google API error"}

        data = response.json()
        google_routes = data.get("routes", [])
        logger.info(f"[GOOGLE ROUTES RECEIVED] Count={len(google_routes)}")

        if not google_routes:
            return {"message": "No routes returned"}

        all_routes = []
        best_route = None

        # SELECT BEST ROUTE (direct or with intermediates)
        if not intermediate_locations:
            # Direct route - select best by objective
            for idx, r in enumerate(google_routes):
                distance_km = r.get("distanceMeters", 0) / 1000
                duration_hr = convertDuration(r.get("duration"))
                encoded = r.get("polyline", {}).get("encodedPolyline")
                # decoded_path = polyline.decode(encoded)
                # decoded_path_dicts = [{"lat": lat, "lng": lng} for lat, lng in decoded_path]
                
                fuel_cost = distance_km * 0.14

                route_data = {
                    "distance": round(distance_km, 2),
                    "duration": round(duration_hr, 2),
                    "cost": round(fuel_cost, 2),
                    "path": encoded
                }
                all_routes.append(route_data)
            
            if objective == "cost" or objective == "cheapest":
                best_route = min(all_routes, key=lambda x: x["cost"])
            elif objective in ["duration", "time"]:
                best_route = min(all_routes, key=lambda x: x["duration"])
            else:
                best_route = min(all_routes, key=lambda x: x["distance"])
            
            print("Google Route is being served as best route without LP optimization since no intermediates provided.")

        else:
            # With intermediates - USE LP SOLVER to SELECT BEST ROUTE
            logger.info("[USING LP SOLVER FOR ROUTE SELECTION]")
            route_options = []
            
            for idx, r in enumerate(google_routes):
                distance_km = r.get("distanceMeters", 0) / 1000
                duration_hr = convertDuration(r.get("duration"))
                encoded = r.get("polyline", {}).get("encodedPolyline")
                # decoded_path = polyline.decode(encoded)
                # decoded_path_dicts = [{"lat": lat, "lng": lng} for lat, lng in decoded_path]

                fuel_cost = distance_km * 0.14

                route_data = {
                    "distance": round(distance_km, 2),
                    "duration": round(duration_hr, 2),
                    "path": encoded,
                    "cost": round(fuel_cost, 2),
                    "from": source,
                    "to": destination,
                    "via": intermediate_locations
                }
                route_options.append(route_data)
                all_routes.append(route_data)

            logger.info(f"[ROUTES AVAILABLE] {len(route_options)} alternatives")

            # LP Solver to select best
            if len(route_options) > 1:
                model = LpProblem("Route_Selection", LpMinimize)
                route_vars = LpVariable.dicts("route_choice", range(len(route_options)), cat="Binary")
                
                if objective == "cost" or objective == "cheapest":
                    model += lpSum(route_vars[i] * route_options[i]["cost"] for i in range(len(route_options)))
                elif objective in ["duration", "time"]:
                    model += lpSum(route_vars[i] * route_options[i]["duration"] for i in range(len(route_options)))
                else:
                    model += lpSum(route_vars[i] * route_options[i]["distance"] for i in range(len(route_options)))
                
                model += lpSum(route_vars[i] for i in range(len(route_options))) == 1
                
                try:
                    model.solve(PULP_CBC_CMD(msg=0))
                    if model.status == 1:
                        for i in range(len(route_options)):
                            if route_vars[i].varValue == 1:
                                best_route = route_options[i]
                                logger.info(f"[LP OPTIMIZED] Selected route {i}")
                                break
                    else:
                        best_route = route_options[0]
                except Exception as e:
                    logger.error(f"[LP ERROR] {e}")
                    best_route = route_options[0]
            else:
                best_route = route_options[0] if route_options else None
            
            print("Best route selected using LP optimization based on provided intermediates and objective.")

        return {
            "message": "Routes calculated successfully",
            "data": {
                "source": source,
                "destination": destination,
                "intermediate_locations": intermediate_locations,
                "best_route": best_route,
                "routes": all_routes
            }
        }

    except Exception as e:
        logger.error(f"[ERROR] {e}", exc_info=True)
        return {"message": "Computing route failed"}
        

def convertDuration(duration_str):
    if not duration_str or not duration_str.endswith("s"):
        return None
    seconds = int(duration_str.replace("s", ""))
    return seconds / 3600 