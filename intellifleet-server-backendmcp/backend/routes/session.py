
from fastapi import APIRouter, Depends, HTTPException
from ..routes.auth import get_current_user
from ..database.database import fetch_persistent_routes_by_user, fetch_multimodal_routes_by_user
from fastapi.responses import JSONResponse

router = APIRouter(tags=["Session"])

def build_route_session_state(user_id: int):
        
    try:
        persistent_routes = fetch_persistent_routes_by_user(user_id)
        multimodal_routes = fetch_multimodal_routes_by_user(user_id)

        session_routes = []
        alternative_routes = []

        # Separate normal & alternative persistent routes
        for route in persistent_routes:
            route_data = route["route_data"]

            if route.get("parent_route_id"):
                alternative_routes.append({
                    "route_id": route["route_id"],
                    "parent_route_id": route["parent_route_id"],
                    "data": route_data,
                    "is_active": route["is_active"],
                    "created_at": route["created_at"]
                })
            else:
                session_routes.append({
                    "route_id": route["route_id"],
                    "data": route_data,
                    "is_active": route["is_active"],
                    "created_at": route["created_at"]
                })

        return {
            "routes": session_routes,
            "alternative_routes": alternative_routes,
            "multimodal_routes": multimodal_routes
        }
    
    except Exception as e:
        return {"message": "Internal server error. Not able to fetch routes."}

# ======================================================= API ======================================================

@router.get("/route_session")
async def restore_route_session(current_user = Depends(get_current_user)):
    """
    Restores all routes (persistent + alternative + multimodal)
    into session-friendly format
    """
    try:

        user_id = current_user.get("user_id")
        
        if not user_id:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "Invalid token: user_id not found"
                },
            )
        

    
        session_data = build_route_session_state(user_id)

        return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "Route session restored successfully",
                    "data": session_data
                },
            )
    

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Unable to fetch all routes"
            },
        )