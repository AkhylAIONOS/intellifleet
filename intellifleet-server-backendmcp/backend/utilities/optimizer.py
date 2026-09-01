from pulp import *
from backend.config.logger import logger

async def optimize(nodes, edges, start, end, objective, via=None):
    """
    Optimize route from start to end node.
    
    Args:
        nodes: Dict of node_id -> (lat, lon)
        edges: Dict of (from, to) -> {properties}
        start: Starting node
        end: Ending node
        objective: "cost" | "time" | "distance" | "fastest"
        via: Optional intermediate node(s) to pass through
    
    Returns:
        List of edges in optimized route
    """
    model = LpProblem("Logistics_Optimization", LpMinimize)

    # Create binary variables for each edge
    x = LpVariable.dicts("route", edges.keys(), cat="Binary")

    # Set objective function
    if objective == "cost" or objective == "cheapest":
        model += lpSum(x[e] * edges[e].get("fuel", 0) for e in edges)
    elif objective == "distance":
        model += lpSum(x[e] * edges[e].get("distance", 0) for e in edges)
    else:
        model += lpSum(x[e] * edges[e].get("time", 0) for e in edges)

    # Flow conservation constraints
    for n in nodes:
        inflow = lpSum(x[(i, j)] for (i, j) in edges if j == n and (i, j) in x)
        outflow = lpSum(x[(i, j)] for (i, j) in edges if i == n and (i, j) in x)

        if n == start:
            # Start node: outflow = inflow + 1
            model += outflow - inflow == 1
        elif n == end:
            # End node: inflow = outflow + 1
            model += inflow - outflow == 1
        else:
            # Intermediate nodes: inflow = outflow
            model += inflow == outflow

    # Via constraint: if intermediate node is specified, route must pass through it
    if via:
        if isinstance(via, list):
            for v in via:
                inflow_via = lpSum(x[(i, j)] for (i, j) in edges if j == v and (i, j) in x)
                model += inflow_via == 1
        else:
            inflow_via = lpSum(x[(i, j)] for (i, j) in edges if j == via and (i, j) in x)
            model += inflow_via == 1

    # Solve
    try:
        model.solve(PULP_CBC_CMD(msg=0))
    except Exception as e:
        logger.error(f"Solver error: {e}")
        return []

    # Extract solution
    if model.status != 1:  # 1 = Optimal solution found
        logger.warning(f"No optimal solution found. Status: {model.status}")
        return []

    route = []
    for e in edges:
        if x[e].varValue == 1:
            route.append(edges[e])

    return sorted(route, key=lambda r: (r.get("from"), r.get("to")))