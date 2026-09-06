from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from backend.routes.api import router as chat
from backend.routes.auth import router as auth
from backend.routes.upload.uploadCSV import router as upload
from backend.routes.vehicles.vehicle_api import router as vehicle_api
# from backend.routes.route_map.testAIR import router as air_route
# from backend.routes.clearAll import router as clearall
# from backend.routes.googleRoute import router as routes
from backend.routes.session import router as session
# from backend.routes.multimodalVehicle import router as mvehicle
# from backend.routes.warehouse import router as warehouse_router
import sqlite3
from contextlib import asynccontextmanager
from backend.routes.route_map.route_query import router as route_query
from backend.api.chat_api import router as chat_router
from backend.routes.upload.route_upload2 import router as route_upload_json
from backend.routes.agent_routes import router as history
from backend.routes.vehicles.partial_vehicle import router as partial_vehicle
from backend.routes.disruption.disruption import disruption_router
from backend.config.config import settings
from backend.planning.routes import router as planning_router
from backend.routes.upload.network_upload import router as network_upload_router

@asynccontextmanager
async def lifespan(app: FastAPI):

    from backend.database.database import init_db
    from backend.planning.database import migrate_planning_schema
    init_db()
    migrate_planning_schema()

    # DB setup
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    app.state.db = conn

    # 🔥 Initialize supervisor HERE
    from backend.agents.supervisor import supervisor
    await supervisor.initialize()

    yield

    # Shutdown cleanup
    app.state.db.close()


app = FastAPI(title="IntelliFleet", lifespan=lifespan)

allowed_origins = [
    "https://intellifleet-web.onrender.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://unprecipitate-liquidly-randal.ngrok-free.dev",
]
frontend_origin = (settings.FRONTEND_URL or "").strip().rstrip("/")
if frontend_origin and frontend_origin not in allowed_origins:
    allowed_origins.append(frontend_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat)
app.include_router(auth)
app.include_router(upload)
# app.include_router(routes)
app.include_router(vehicle_api)
# app.include_router(agent_router)
# app.include_router(air_route)
# app.include_router(clearall)
app.include_router(session)
# app.include_router(mvehicle)
# app.include_router(warehouse_router)
app.include_router(route_query)
# app.include_router(langraph_agent)
app.include_router(chat_router) 
app.include_router(route_upload_json)
app.include_router(history)
app.include_router(partial_vehicle)
app.include_router(disruption_router)
app.include_router(planning_router)
app.include_router(network_upload_router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
