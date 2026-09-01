import json
import uuid
from typing import Any, Dict, Optional

from backend.routes.vehicles.final_vehicle import assign_vehicles_multi_segment
from backend.config.logger import logger
import redis

import json
import uuid
from typing import Dict, Any

from backend.routes.vehicles.final_vehicle import assign_vehicles_multi_segment
from fastapi.responses import JSONResponse


# decode_responses=True gives us strings instead of bytes
r = redis.Redis(
    host="localhost",
    port=6379,
    db=1,
    decode_responses=True
)

def get_redis():
    """Return Redis instance (singleton-style)."""
    return r

r = get_redis()

SESSION_TTL_SEC = 7200


async def start_partial_assignment(
    user_id: int,
    source: str,
    destination: str,
    required_capacity: int,
    objective: str,
    vehicle_type: Optional[str] = None,
) -> Dict[str, Any]:

    # ── Run full solver ───────────────────────────────────────────────────────
    result = await assign_vehicles_multi_segment(
        user_id=user_id,
        source=source,
        destination=destination,
        required_capacity=required_capacity,
        objective=objective,
        vehicle_type=vehicle_type,
    )

    if not result["success"]:
        return {
            "success": False,
            "response_text": result.get("response_text", "Assignment failed."),
            "actions": [],
        }

    segments       = result["data"]["segments"]
    total_segments = len(segments)
    full_summary   = result.get("response_text", "")
    data           = result["data"]

    # ── CASE A: Single segment ────────────────────────────────────────────────
    if total_segments == 1:
        return {
            "success": True,
            "response_text": full_summary,
            "actions": [
                {
                    "type": "partial_assignment_start",
                    "data": {
                        "session_id":        None,
                        "partial":           True,
                        "route_chain":       data["route_chain"],
                        "overall_departure": data["overall_departure"],
                        "final_arrival":     data["final_arrival"],
                        "total_cost":        data["total_cost"],
                        "total_segments":    1,
                        "segments":          segments,
                    }
                },
                {
                    "type": "animate_segment",
                    "data": {
                        "session_id":     None,
                        "partial":        True,   # no more segments after this
                        "segment_index":  0,
                        "total_segments": 1,
                        "segment":        segments[0],
                    }
                }
            ],
        }

    # ── CASE B: Multiple segments — store in Redis, surface first segment ─────
    session_id = str(uuid.uuid4())
    r.setex(
        f"multi_seg:{session_id}",
        SESSION_TTL_SEC,
        json.dumps({"index": 0, "segments": segments}),
    )

    logger.info(
        f"[PARTIAL] session={session_id} | {total_segments} segments stored "
        f"| first: {segments[0]['from']} → {segments[0]['to']}"
    )

    return {
        "success": True,
        "response_text": full_summary,
        "actions": [
            {
                "type": "partial_assignment_start",
                "data": {
                    "session_id":        session_id,
                    "partial":           False,
                    "route_chain":       data["route_chain"],
                    "overall_departure": data["overall_departure"],
                    "final_arrival":     data["final_arrival"],
                    "total_cost":        data["total_cost"],
                    "total_segments":    total_segments,
                    "segments":          segments,
                }
            },
            {
                "type": "animate_segment",
                "data": {
                    "session_id":     session_id,
                    "partial":        False,
                    "segment_index":  0,
                    "total_segments": total_segments,
                    "segment":        segments[0],
                }
            }
        ],
    }


async def get_next_partial_segment(session_id: str) -> Dict[str, Any]:

    key = f"multi_seg:{session_id}"
    raw = r.get(key)

    if not raw:
        return {"error": "Invalid or expired session_id."}

    data     = json.loads(raw)
    cur_idx  = data["index"]
    segs     = data["segments"]
    next_idx = cur_idx + 1

    if next_idx >= len(segs):
        r.delete(key)
        return {"error": "All segments have already been delivered."}

    is_last = next_idx == len(segs) - 1

    # Advance pointer (clean up after final delivery)
    data["index"] = next_idx
    if is_last:
        r.delete(key)
    else:
        r.setex(key, SESSION_TTL_SEC, json.dumps(data))

    logger.info(
        f"[PARTIAL] session={session_id} | segment {next_idx + 1}/{len(segs)} "
        f"| {segs[next_idx]['from']} → {segs[next_idx]['to']} | last={is_last}"
    )

    return {
        "session_id":     session_id,
        "partial":        is_last,
        "segment_index":  next_idx,
        "total_segments": len(segs),
        "segment":        segs[next_idx],
    }

from fastapi import APIRouter
# from backend.routes.partial_assignment import start_partial_assignment

router = APIRouter(tags=["Vehicles"])


@router.get("/assign-partial-next")
async def get_next_segment(session_id: str):
    try:
        result = await get_next_partial_segment(session_id)

        # If segment is None → no more segments found
        if result is None:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "No next segment found for the given session_id.",
                    "session_id": session_id
                }
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "session_id": session_id,
                "data": result
            }
        )

    except Exception as e:
        # Log the exception if you have logger
        logger.error(f"Error fetching next segment: {str(e)}")

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error while fetching next segment.",
                "session_id": session_id
            }
        )