from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

from backend.routes.auth import router as auth
# from backend.routes.route_map.testAIR import router as air_route
# from backend.routes.clearAll import router as clearall
# from backend.routes.googleRoute import router as routes
from backend.routes.session import router as session
# from backend.routes.multimodalVehicle import router as mvehicle
# from backend.routes.warehouse import router as warehouse_router
import sqlite3
from contextlib import asynccontextmanager


from backend.config.config import settings
from backend.planning.routes import router as planning_router
from backend.fedex.routes import router as fedex_router
from backend.fedex.telemetry import runtime as fedex_runtime
from backend.control_tower.routes import router as control_tower_router, monitor as control_tower_monitor
import asyncio
from contextlib import suppress

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

    # Fail closed if the authoritative workbook is unavailable.
    from backend.client_network import network
    network()

    fedex_task = asyncio.create_task(fedex_runtime.run())
    control_tower_task = asyncio.create_task(control_tower_monitor())
    try:
        yield
    finally:
        fedex_task.cancel()
        control_tower_task.cancel()
        with suppress(asyncio.CancelledError):
            await control_tower_task
        with suppress(asyncio.CancelledError):
            await fedex_task

    # Shutdown cleanup
    app.state.db.close()


app = FastAPI(title="IntelliFleet", lifespan=lifespan)

allowed_origins = [
    "https://intellifleet-web.onrender.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5178",
    "http://127.0.0.1:5178",
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

from backend.client_api import router as client_network_router
app.include_router(client_network_router)
# Legacy topology-generating routers are intentionally not registered.
app.include_router(auth)

# app.include_router(routes)

# app.include_router(agent_router)
# app.include_router(air_route)
# app.include_router(clearall)
app.include_router(session)
# app.include_router(mvehicle)
# app.include_router(warehouse_router)

# app.include_router(langraph_agent)





app.include_router(planning_router)

app.include_router(fedex_router)
app.include_router(control_tower_router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

from backend.operations.routes import router as operations_router
app.include_router(operations_router)
