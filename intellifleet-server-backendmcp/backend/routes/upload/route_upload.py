from fastapi import APIRouter, UploadFile, File, Depends
import pandas as pd
import io
from ...config.logger import logger
from ..auth import get_current_user
from ...database.database import get_warehouse_by_name
from ..route_map.googleRoute import calculate_route_with_google
# from ..route_map.airRoute import combined_route_function
from ..route_map.testAIR import combined_route_function
from ...models.airRouteSchema import AirRouteRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional


router = APIRouter()


# ---------------- CSV LOADER ---------------- #

def load_csv(file: UploadFile):
    if not file.filename.endswith(".csv"):
        return None, "File must be CSV"

    content = file.file.read().decode("utf-8")
    df = pd.read_csv(io.StringIO(content))
    df.columns = [c.strip() for c in df.columns]
    return df, None


# ---------------- VALIDATE COLUMNS ---------------- #

REQUIRED_COLS = {"Source", "Destination", "IntermediateLocation", "RouteType"}

def validate_columns(df):
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        return f"Missing columns: {', '.join(missing)}"
    return None


# def parse_intermediate(mid):
#     if pd.isna(mid) or str(mid).strip() == "":
#         return None

#     mid_str = str(mid).strip()

#     # Case 1: [Mumbai, Hyderabad]
#     if mid_str.startswith("[") and mid_str.endswith("]"):
#         inner = mid_str[1:-1]
#         return [x.strip() for x in inner.split(",") if x.strip()]

#     # Case 2: explicit comma-separated
#     if "," in mid_str:
#         return [x.strip() for x in mid_str.split(",") if x.strip()]

#     # Case 3: pipe-separated
#     if "|" in mid_str:
#         return [x.strip() for x in mid_str.split("|") if x.strip()]

#     return [mid_str]

def parse_intermediate(mid):
    # Case 0: None or blank
    if mid is None:
        return None

    # Case 1: Already a Python list (JSON body)
    if isinstance(mid, list):
        return [str(x).strip() for x in mid if str(x).strip()]

    # Convert CSV cell to clean string
    mid_str = str(mid).strip()

    if mid_str == "" or mid_str.lower() in ["nan", "none"]:
        return None

    # Case 2: [Mumbai, Hyderabad]
    if mid_str.startswith("[") and mid_str.endswith("]"):
        inner = mid_str[1:-1]
        return [x.strip() for x in inner.split(",") if x.strip()]

    # Case 3: comma-separated
    if "," in mid_str:
        return [x.strip() for x in mid_str.split(",") if x.strip()]

    # Case 4: pipe-separated
    if "|" in mid_str:
        return [x.strip() for x in mid_str.split("|") if x.strip()]

    # Case 5: single value
    return [mid_str]


# ============================================================
#  MAIN UPLOAD FUNCTION (ROAD + AIR GOOGLE ROUTES)
# ============================================================


# async def upload_routes_function(user_id: int, file: UploadFile):

#     df, err = load_csv(file)
#     if err:
#         return {"success": False, "message": err}

#     err = validate_columns(df)
#     if err:
#         return {"success": False, "message": err}

#     inserted = 0
#     errors = []

#     road_routes = []
#     multimodal_routes = []
#     air_intermediate_route = []

#     # LOOP OVER EACH ROW
#     for idx, row in df.iterrows():

#         try:
#             src = str(row["Source"]).strip()
#             dest = str(row["Destination"]).strip()
#             mid = row["IntermediateLocation"]
#             route_type = str(row["RouteType"]).strip().lower()

#             # ===============================
#             # VALIDATE SOURCE & DESTINATION
#             # ===============================
#             src_warehouse = get_warehouse_by_name(user_id, src)
#             dest_warehouse = get_warehouse_by_name(user_id, dest)

#             error_parts = []

#             if not src_warehouse:
#                 error_parts.append(f"Source '{src}' not found")

#             if not dest_warehouse:
#                 error_parts.append(f"Destination '{dest}' not found")

#             # ===============================
#             # SAFE INTERMEDIATE PARSING
#             # ===============================
#             try:
#                 mids = parse_intermediate(mid) if mid else []
#             except Exception:
#                 mids = []

#             if mids is None:
#                 mids = []

#             # ===============================
#             # VALIDATE INTERMEDIATES
#             # ===============================
#             invalid_intermediates = []
#             for m in mids:
#                 wh = get_warehouse_by_name(user_id, m)
#                 if not wh:
#                     invalid_intermediates.append(m)

#             if invalid_intermediates:
#                 error_parts.append(
#                     f"Intermediate warehouse(s) not found: {', '.join(invalid_intermediates)}"
#                 )

#             # If any warehouse errors → skip row
#             if error_parts:
#                 errors.append(
#                     f"Row {idx+1}: " + " | ".join(error_parts)
#                 )
#                 continue

#             # ===============================
#             # BUILD WAYPOINTS
#             # ===============================
#             waypoints = [src]
#             if mids:
#                 waypoints.extend(mids)
#             waypoints.append(dest)

#             # ===============================
#             # ROAD ROUTE
#             # ===============================
#             if route_type in ("road", "land"):

#                 result = await calculate_route_with_google(
#                     user_id, waypoints, objective="duration"
#                 )

#                 if not result.get("route_id"):
#                     errors.append(f"Row {idx+1}: Road route creation failed")
#                     continue

#                 road_routes.append(result)
#                 inserted += 1

#             # ===============================
#             # AIR ROUTE
#             # ===============================
#             elif route_type == "air":

#                 air_payload = AirRouteRequest(
#                     source=src,
#                     destination=dest,
#                     intermediate_locations=mids,
#                     objective="duration"
#                 )

#                 result = await combined_route_function(
#                     air_payload, user_id
#                 )

#                 if result.get("route_id"):
#                     multimodal_routes.append(result)
#                     inserted += 1
#                 elif result.get("routes"):
#                     air_intermediate_route.append(result)
#                     inserted += 1
#                 else:
#                     errors.append(f"Row {idx+1}: Air route creation failed")

#             # ===============================
#             # INVALID ROUTE TYPE
#             # ===============================
#             else:
#                 errors.append(
#                     f"Row {idx+1}: Invalid RouteType '{route_type}'"
#                 )
#                 continue

#         except Exception as e:
#             logger.error(f"Error processing row {idx+1}: {e}")
#             errors.append(
#                 f"Row {idx+1}: Unexpected error - {str(e)}"
#             )

#     # ==========================================
#     # FINAL MESSAGE BUILDING
#     # ==========================================
#     failed_count = len(errors)

#     if failed_count > 0:
#         final_message = (
#             f"Successfully uploaded {inserted} route(s) from your CSV file. "
#             f"{failed_count} row(s) failed. "
#             f"Issues: " + " || ".join(errors)
#         )
#     else:
#         final_message = (
#             f"Successfully uploaded {inserted} route(s) from your CSV file."
#         )

#     return {
#         "success": True,
#         "message": final_message,
#         "data": {
#             "road_routes": road_routes,
#             "multimodal_routes": multimodal_routes,
#             "air_intermediate_route": air_intermediate_route
#         },
#         "errors": errors
#     }


async def upload_routes_function(user_id: int, file: UploadFile):

    df, err = load_csv(file)
    if err:
        return {"success": False, "message": err}

    err = validate_columns(df)
    if err:
        return {"success": False, "message": err}

    inserted = 0
    errors = []

    road_routes = []
    multimodal_routes = []
    air_intermediate_route = []

    # ===============================
    # PRE-COLLECT ALL CSV PAIRS
    # So we know which reverses already exist
    # ===============================
    csv_route_pairs = set()
    for _, row in df.iterrows():
        try:
            src = str(row["Source"]).strip().lower()
            dest = str(row["Destination"]).strip().lower()
            rt = str(row["RouteType"]).strip().lower()
            csv_route_pairs.add((src, dest, rt))
        except Exception:
            pass

    # ===============================
    # HELPER: CREATE A SINGLE ROUTE
    # ===============================
    async def create_route(src, dest, mids, route_type, label):
        """
        Creates one road or air route.
        Returns (success: bool, result: dict, error_msg: str | None)
        """
        waypoints = [src] + (mids or []) + [dest]

        if route_type in ("road", "land"):
            result = await calculate_route_with_google(
                user_id, waypoints, objective="duration"
            )
            if result.get("route_id"):
                return True, result, None
            return False, {}, f"{label}: Road route creation failed"

        elif route_type == "air":
            air_payload = AirRouteRequest(
                source=src,
                destination=dest,
                intermediate_locations=mids,
                objective="duration"
            )
            result = await combined_route_function(air_payload, user_id)

            if result.get("route_id"):
                return True, result, None
            elif result.get("routes"):
                return True, result, None          # intermediate air result
            return False, {}, f"{label}: Air route creation failed"

        return False, {}, f"{label}: Invalid RouteType '{route_type}'"

    # ===============================
    # HELPER: STORE RESULT BY TYPE
    # ===============================
    def store_result(result, route_type):
        if route_type in ("road", "land"):
            road_routes.append(result)
        elif route_type == "air":
            if result.get("route_id"):
                multimodal_routes.append(result)
            else:
                air_intermediate_route.append(result)

    # ===============================
    # MAIN ROW LOOP
    # ===============================
    for idx, row in df.iterrows():
        try:
            src = str(row["Source"]).strip()
            dest = str(row["Destination"]).strip()
            mid = row["IntermediateLocation"]
            route_type = str(row["RouteType"]).strip().lower()

            # --- Validate source & destination ---
            src_warehouse = get_warehouse_by_name(user_id, src)
            dest_warehouse = get_warehouse_by_name(user_id, dest)
            error_parts = []

            if not src_warehouse:
                error_parts.append(f"Source '{src}' not found")
            if not dest_warehouse:
                error_parts.append(f"Destination '{dest}' not found")

            # --- Parse intermediates ---
            try:
                mids = parse_intermediate(mid) if mid else []
            except Exception:
                mids = []
            if mids is None:
                mids = []

            # --- Validate intermediates ---
            invalid_intermediates = [
                m for m in mids if not get_warehouse_by_name(user_id, m)
            ]
            if invalid_intermediates:
                error_parts.append(
                    f"Intermediate warehouse(s) not found: {', '.join(invalid_intermediates)}"
                )

            if error_parts:
                errors.append(f"Row {idx+1}: " + " | ".join(error_parts))
                continue

            # ===============================
            # CREATE FORWARD ROUTE
            # ===============================
            ok, result, err_msg = await create_route(
                src, dest, mids, route_type, f"Row {idx+1}"
            )
            if not ok:
                errors.append(err_msg)
                continue

            store_result(result, route_type)
            inserted += 1

            # ===============================
            # CREATE REVERSE ROUTE IF MISSING
            # Intermediates are reversed: A→[B,C]→D  →  D→[C,B]→A
            # ===============================
            rev_mids = list(reversed(mids)) if mids else []

            reverse_exists = (dest.lower(), src.lower(), route_type) in csv_route_pairs

            if not reverse_exists:
                rev_ok, rev_result, rev_err = await create_route(
                    dest, src, rev_mids, route_type,
                    f"Row {idx+1} (reverse {dest}→{src})"
                )
                if rev_ok:
                    store_result(rev_result, route_type)
                    inserted += 1
                else:
                    errors.append(rev_err)

        except Exception as e:
            logger.error(f"Error processing row {idx+1}: {e}")
            errors.append(f"Row {idx+1}: Unexpected error - {str(e)}")

    # ==========================================
    # FINAL RESPONSE
    # ==========================================
    failed_count = len(errors)
    if failed_count > 0:
        final_message = (
            f"Successfully uploaded {inserted} route(s) from your CSV file. "
            f"{failed_count} row(s) failed. "
            f"Issues: " + " || ".join(errors)
        )
    else:
        final_message = f"Successfully uploaded {inserted} route(s) from your CSV file."

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