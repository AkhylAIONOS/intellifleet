import json
from typing import List, Dict, Tuple
from pulp import *
from backend.config.logger import logger
from backend.database.database import load_edges_and_nodes, load_edges_and_nodes_air
from backend.routes.route_map.googleRoute import calculate_route_with_google
from backend.routes.route_map.testAIR import *

# ================================================================
# 2. LP SOLVER (YOU PROVIDED) — NO CHANGE
# ================================================================
async def optimize(nodes, edges, start, end, objective, via=None):
    model = LpProblem("Logistics_Optimization", LpMinimize)
    x = LpVariable.dicts("route", edges.keys(), cat="Binary")

    # Objective
    if objective in ("cost", "cheapest"):
        model += lpSum(x[e] * edges[e].get("fuel", 0) for e in edges)
    elif objective == "distance":
        model += lpSum(x[e] * edges[e].get("distance", 0) for e in edges)
    else:
        model += lpSum(x[e] * edges[e].get("time", 0) for e in edges)

    # Flow constraints
    for n in nodes:
        inflow = lpSum(x[(i, j)] for (i, j) in edges if j == n)
        outflow = lpSum(x[(i, j)] for (i, j) in edges if i == n)

        if n == start:
            model += outflow - inflow == 1
        elif n == end:
            model += inflow - outflow == 1
        else:
            model += inflow == outflow

    # VIA constraint
    if via:
        if isinstance(via, list):
            for v in via:
                inflow_v = lpSum(x[(i, j)] for (i, j) in edges if j == v)
                model += inflow_v == 1
        else:
            inflow_v = lpSum(x[(i, j)] for (i, j) in edges if j == via)
            model += inflow_v == 1

    try:
        model.solve(PULP_CBC_CMD(msg=0))
    except Exception as e:
        logger.error(f"Solver error: {e}")
        return []

    if model.status != 1:
        logger.warning(f"No optimal solution found: status = {model.status}")
        return []

    route = []
    for e in edges:
        if x[e].varValue == 1:
            route.append(edges[e])

    # SORT EDGES IN CORRECT SEQUENCE
    # route = sorted(route, key=lambda r: (r["from"], r["to"]))
    return route


# ================================================================
# 3. EXTRACT WAYPOINT CHAIN FROM OPTIMIZER RESULT
# ================================================================
def extract_waypoints(route_edges, start):
    if not route_edges:
        return None

    # Build adjacency for quick lookup
    edge_map = {e["from"]: e for e in route_edges}

    waypoints = [start]
    current = start

    while current in edge_map:
        next_node = edge_map[current]["to"]
        waypoints.append(next_node)
        current = next_node

    return waypoints


# ================================================================
# 4. GEO ROUTE LOGIC — CREATES WAYPOINTS USING LP
# ================================================================
async def build_waypoints(user_id: int, source: str, destination: str,
                           via_list: List[str], objective: str):
    """
    Build route purely from route_summary graph using LP solver.
    """

    nodes, edges = load_edges_and_nodes(user_id)

    # If user forces an ordered chain
    if via_list:
        return [source] + via_list + [destination]

    # Try finding best indirect route using LP solver
    route_edges = await optimize(
        nodes=nodes,
        edges=edges,
        start=source,
        end=destination,
        objective=objective
    )

    if not route_edges:
        return None

    waypoints = extract_waypoints(route_edges, start=source)
    return waypoints

async def build_waypoints_air(user_id: int, source: str, destination: str,
                           via_list: List[str], objective: str):
    """
    Build route purely from route_summary graph using LP solver.
    """

    nodes, edges = load_edges_and_nodes_air(user_id)

    # If user forces an ordered chain
    if via_list:
        return [source] + via_list + [destination]

    # Try finding best indirect route using LP solver
    route_edges = await optimize(
        nodes=nodes,
        edges=edges,
        start=source,
        end=destination,
        objective=objective
    )

    if not route_edges:
        return None

    waypoints = extract_waypoints(route_edges, start=source)
    return waypoints

# ================================================================
# 5. MAIN WRAPPER — RETURNS DB OR GOOGLE RESULT
# ================================================================
async def smart_route_handler(
    user_id: int,
    source: str,
    destination: str,
    via_list: Optional[List[str]] = None,
    objective: Optional[str] = "duration"
):
    """
    1. Build waypoint chain using stored legs.
    2. If exact chain exists in DB → return DB.
    3. Otherwise fetch from Google.
    """

    logger.info(f"[BUILD] Source={source}, Destination={destination}, Via={via_list}")

    # STEP 1 — Build waypoint chain using LP + graph
    waypoints = await build_waypoints(
        user_id=user_id,
        source=source,
        destination=destination,
        via_list=via_list,
        objective=objective
    )

    if not waypoints:
        return {"message": "No possible route from the route network csv uploaded. Try uploading new route csv or add routes above."}

    logger.info(f"[WAYPOINTS BUILT] {waypoints}")

    logger.info(f"[GOOGLE CALL] Fetching best route for {waypoints}")
    result = await calculate_route_with_google(
        user_id,
        waypoints,
        objective
    )

    return result

async def smart_route_handler_air(
    user_id: int,
    source: str,
    destination: str,
    via_list: Optional[List[str]] = None,
    objective: Optional[str] = "duration"
):
    """
    Smart route handler without Google routing.
    Flow:
        1. Build waypoint chain using LP + stored legs.
        2. Create AirRouteRequest payload from waypoints.
        3. Call combined_route_function().
    """

    logger.info(f"[BUILD] Source={source}, Destination={destination}, Via={via_list}")

    # -----------------------------------------------------------
    # STEP 1 — Build waypoint chain using LP + graph
    # -----------------------------------------------------------
    waypoints = await build_waypoints_air(
        user_id=user_id,
        source=source,
        destination=destination,
        via_list=via_list,
        objective=objective
    )

    print(f"==>> waypoints:  {waypoints}")

    if not waypoints or len(waypoints) < 2:
        return {
            "status": False,
            "message": "No possible route from the stored route network. "
                       "Upload CSV route network or add routes manually."
        }

    logger.info(f"[WAYPOINTS BUILT] {waypoints}")

    # -----------------------------------------------------------
    # STEP 2 — Convert waypoints → AirRouteRequest
    # -----------------------------------------------------------
    # Example:
    # waypoints = ["A", "B", "C", "D"]
    # source = "A"
    # destination = "D"
    # intermediate_locations = ["B", "C"]

    source_loc = waypoints[0]
    print(f"==>> source_loc:  {source_loc}")
    destination_loc = waypoints[-1]
    print(f"==>> destination_loc:  {destination_loc}")
    intermediate_locs = waypoints[1:-1]  # everything between
    print(f"==>> intermediate_locs:  {intermediate_locs}")

    payload = AirRouteRequest(
        
        source=source_loc,
        destination=destination_loc,
        intermediate_locations=intermediate_locs,
        objective=objective
    )

    logger.info(f"[PAYLOAD READY] {payload}")

    # -----------------------------------------------------------
    # STEP 3 — Call the combined multimodal routing engine
    # -----------------------------------------------------------
    result = await combined_route_function(payload, user_id)

    # -----------------------------------------------------------
    # STEP 4 — Return final result
    # -----------------------------------------------------------
    return result