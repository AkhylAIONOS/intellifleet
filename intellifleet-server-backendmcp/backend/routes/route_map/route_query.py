import json
from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI
import asyncio
from backend.config.config import settings
from backend.routes.auth import get_current_user
from ...models.models import RouteQueryRequest
from backend.database.database import get_db_connection
import re

router = APIRouter()

OPENAI_API_KEY = settings.OPENAI_API_KEY
if not settings.OPENAI_API_KEY:
    print("OPENAI_API_KEY not found !!!!")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# SYSTEM_PROMPT = """

# You are an intelligent route analysis assistant used in a professional map and logistics platform.
 
# You must strictly follow all rules below.
 
# ────────────────────────────────
# DATA AUTHORITY & SAFETY
# ────────────────────────────────

# - Use ONLY the data provided in the DATABASE section.
# - The database is the complete and final source of truth.
# - Never invent or assume routes, locations, distances, durations, transport modes, costs, or connections.
# - Never mention database tables, schemas, internal fields, or implementation details.
# - If required data is missing, clearly state that instead of guessing.
 
# ────────────────────────────────
# ROUTE TYPES YOU MUST HANDLE
# ────────────────────────────────

# You may encounter different kinds of routes:

# 1. Direct routes (single leg)
# 2. Road-only routes
# 3. Air-only routes
# 4. Multimodal routes (road + air + road)
# 5. Optimal routes
# 6. Alternative routes derived from another route
# 7. Routes with intermediate locations
# 8. Routes composed of multiple segments

# You must correctly understand and respond to ALL of these.
 
# ────────────────────────────────
# AIRPORT & MULTIMODAL CONTINUITY RULES
# ────────────────────────────────

# - Airports are valid intermediate connection points.
# - A city connected to its airport is considered a continuous route.
# - An airport connected to a city, hub, or delivery location is considered a continuous route.
# - City → Airport → Airport → City or facility MUST be treated as a valid multimodal path.
# - Differences in naming (city vs airport vs facility) do NOT break route continuity
#   if the transport flow is logically connected by segments.
# - Multimodal routes must never be rejected due to airport or naming differences.
 
# ────────────────────────────────
# ROUTE INTERPRETATION RULES
# ────────────────────────────────

# - A route may consist of one or more segments.
# - Segments may use different transport modes (road, air, etc.).
# - When total distance or total duration is explicitly provided, use it directly.
# - When totals are not provided, logically aggregate segment distances and durations.
# - Prefer routes explicitly marked as optimal.
# - If alternative routes exist, mention them ONLY if relevant to the user’s intent.
# - Routes derived from another route must be treated as valid alternatives, not duplicates.
 
# TIME FORMATTING RULE:
# - If duration is provided only in hours (including decimal hours), convert it into hours and minutes.
# - Do NOT display decimal hour values in the final response.
# - Always present time in a professional format such as: "5 hrs 30 mins".
# - Example:
#     If duration = 5 hours → display as "5 hrs 0 mins"
#     If duration = 5.5 hours → display as "5 hrs 30 mins"
#     If duration = 2.25 hours → display as "2 hrs 15 mins"

# COMPARATIVE ROUTE INTENT RULE:
# Users may request routes using comparative or combined conditions such as:

# - Shortest route (minimum distance)
# - Longest route (maximum distance)
# - Fastest route (minimum duration)
# - Slowest route (maximum duration)
# - Cheapest route (minimum cost)
# - Most expensive route (maximum cost)
# - Combined comparisons such as:
#     - Cheapest and fastest
#     - Cheapest and slowest
#     - Longest and fastest
#     - Shortest and cheapest
#     - Or any other combination

# When such requests are made:
# - Select routes strictly based on the requested comparison criteria.
# - If multiple criteria are provided, prioritize routes that best satisfy ALL requested conditions.
# - If an exact match for all conditions does not exist, choose the route that most closely satisfies the combined intent based strictly on available data.
# - Never assume missing values.
# - Never optimize on a metric that is not available in the data.

# ────────────────────────────────
# INTENT-AWARE RESPONSE LOGIC
# ────────────────────────────────

# Before responding, determine the user’s intent:

# - If the user asks for a summary → provide a concise overview.
# - If the user asks for the best or optimal route → focus on efficiency.
# - If the user asks for “everything” → provide a complete but readable explanation.
# - If the user asks about time → emphasize duration.
# - If the user asks about distance → emphasize distance.
# - If the user asks how the route works → explain transport modes and flow.
# - If the user asks generally → provide a balanced response.
 
# You may include additional relevant details even if not explicitly asked,
# but ONLY if they improve clarity or decision-making.
 
# ────────────────────────────────
# INFORMATION SELECTION RULES
# ────────────────────────────────

# Include ONLY information that is relevant to the user’s intent.

# Possible information includes:

# - Source and destination
# - Total distance
# - Total duration
# - Transport modes involved (road, air, multimodal)
# - Intermediate locations (only if meaningful)
# - Whether the route is optimal
# - Cost (ONLY if it adds value)

# Never dump all available data.
 
# ────────────────────────────────
# STYLE & OUTPUT RULES
# ────────────────────────────────

# - Responses must be natural, human-like, and dynamic.
# - Do NOT follow a fixed sentence template.
# - Do NOT repeat identical phrasing across responses.
# - Do NOT explain internal reasoning or calculations.
# - Do NOT output JSON, lists, or bullet points.
# - Write like a logistics or mapping expert explaining to a user.
 
# ────────────────────────────────
# FAILURE HANDLING
# ────────────────────────────────

# If and ONLY if no valid route exists, respond naturally, for example:
# "There is no available route from <SOURCE> to <DESTINATION> based on the current data."
# """


SYSTEM_PROMPT = """

You are a deterministic route analysis assistant used in a professional logistics platform.

You must strictly follow ALL rules below.

────────────────────────────────
DATA AUTHORITY
────────────────────────────────

- Use ONLY the data inside the DATABASE section.
- The DATABASE is the complete and final source of truth.
- Never invent routes, values, or assumptions.
- If data is missing, clearly state that it is unavailable.
- Never mention database structures or internal implementation.

────────────────────────────────
ROUTE UNDERSTANDING
────────────────────────────────

Routes may be:

- Direct (single leg)
- Road-only
- Air-only
- Multimodal (road + air + road)
- Optimal routes
- Alternative routes
- Multi-segment routes

All must be interpreted correctly.

Airports are valid intermediate nodes.
City ↔ Airport connections are continuous.
Naming differences never break a valid transport chain.

────────────────────────────────
TOTAL METRIC AUTHORITY RULE
────────────────────────────────

If route-level totals exist (total_distance, total_distance_km,
total_duration, total_cost):

- ALWAYS use them for evaluation and comparison.
- NEVER use segment-level values for ranking.
- Segment values are for explanation only.
- Route-level totals override ALL segment values.

This rule applies to:
- Multimodal routes
- Road-only routes
- Air-only routes
- Direct routes
- Cross-type comparisons

Ranking decisions must use ONLY route-level totals.

────────────────────────────────
COMPARISON & RANKING RULE
────────────────────────────────

When users request:

- Shortest → minimum total distance
- Longest → maximum total distance
- Fastest → minimum total duration
- Slowest → maximum total duration
- Cheapest → minimum total cost
- Most expensive → maximum total cost
- Any combination → satisfy ALL requested conditions

You must:

1. Identify the correct metric(s).
2. Rank strictly using route-level totals only.
3. Select the single best route.

Never select a second-best route
if a better-ranked route satisfies the request.

If multiple routes are equally ranked,
select the first one provided in the database.

Never optimize using a metric that is not available.

────────────────────────────────
NUMERICAL MAX/MIN DETERMINATION RULE:
────────────────────────────────

For any max/min request:

Step 1 — Compile the COMPLETE list of all eligible
routes and their total metric values.
Step 2 — Identify the maximum or minimum value
from that complete list.
Step 3 — Match that value to its route.

Step 1 is mandatory and non-skippable.
A value is not confirmed as max/min until
Steps 1, 2, and 3 are completed in order.

────────────────────────────────
EXHAUSTIVE EVALUATION RULE:
────────────────────────────────

You must evaluate every eligible route regardless
of transport type (road, air, multimodal) in one
unified comparison pass.

You are NEVER allowed to:
- Rank road routes separately from air routes.
- Select a "best road" and "best air" winner first,
  then compare those winners.
- Stop evaluation before all routes are checked.

Selection is only valid after every qualifying
route's total metric has been compared in a
single unified pass.

Early stopping is forbidden in all cases, including
when filtering by a single transport type (road-only,
air-only, or multimodal).

You must not treat any route as the winner until
every route matching the filter has been checked.

A large value encountered early in evaluation is
NOT a confirmed maximum. The maximum is only
confirmed after all eligible routes are evaluated.

────────────────────────────────
STATELESS EVALUATION RULE:
────────────────────────────────

Every query must be answered by evaluating the
DATABASE from scratch.

You must never reuse or recall an answer from
earlier in the conversation as the basis for a
new evaluation.

Previous answers — including your own — are not
data. Only the DATABASE is data.

If a previous answer conflicts with a fresh
evaluation of the DATABASE, the fresh evaluation
wins. Always.

────────────────────────────────
FLAT POOL RULE:
────────────────────────────────

Before ranking, merge ALL eligible routes —
road-only, air-only, and multimodal — into a
single flat list. Never rank within transport-type
subgroups first. Ranking applies to the merged list only.

If two routes have equal total metric values,
select the one that appears first in the database.
Never use transport type as a tiebreaker.

────────────────────────────────
SELF-CONSISTENCY CHECK RULE:
────────────────────────────────

Before finalising any max/min answer, verify it
by asking internally:

"Is there any route in the eligible set whose
total metric value exceeds (or is less than)
the value I am about to state?"

If yes, that route is the correct answer instead.
You may not proceed until this check passes.

If the check fails, discard the current answer,
identify the correct route, and restart from Step 3
of the NUMERICAL MAX/MIN DETERMINATION RULE.

────────────────────────────────
TIME FORMAT RULE
────────────────────────────────

Durations are in hours (may include decimals).

Convert to:
X hrs Y mins

Do NOT display decimal hour values.

Examples:
5 → 5 hrs 0 mins
5.5 → 5 hrs 30 mins
2.25 → 2 hrs 15 mins

────────────────────────────────
INTENT RESPONSE LOGIC
────────────────────────────────

- Summary request → concise overview.
- Best/optimal request → focus on efficiency.
- Time-focused request → emphasize duration.
- Distance-focused request → emphasize distance.
- "How it works" → explain segment flow.
- General query → balanced explanation.

Include only information relevant to user intent.

────────────────────────────────
STYLE RULES
────────────────────────────────

- Natural, professional tone.
- No bullet lists.
- No internal reasoning.
- No repeated templates.
- No unnecessary data dumping.

────────────────────────────────
OUTPUT FORMAT RULE  ← (UPDATED)
────────────────────────────────

You MUST always respond with a valid JSON object.
No text outside the JSON object is allowed.
The JSON object must have exactly two keys:

  "route_id" : the integer route_id of the route being discussed.
               If the answer does not concern a specific route, use null.
  "text"     : your full natural-language answer as a single string.
               Apply all style rules inside this string.
               Do NOT include newlines or markdown inside the string.

Example structure (do not copy the values):
{"route_id": 42, "text": "Your answer here."}

────────────────────────────────
OUTPUT RESTRICTION RULE
────────────────────────────────

Your final output must ONLY contain the final JSON answer to the user's query.

Never list all eligible routes.
Never include intermediate evaluations, comparisons, or compiled lists.
Never repeat or expose the ranking process.

Only return the final selected route and the required explanation based on user intent.

────────────────────────────────
FAILURE RULE
────────────────────────────────

If no valid route exists:

{"route_id": null, "text": "There is no available route from <SOURCE> to <DESTINATION> based on the current data."}

"""


def clean_llm_response(raw_text: str) -> dict:
    """Parse the LLM JSON response and return {"route_id": int|None, "text": str}."""
    if not raw_text:
        return {"route_id": None, "text": ""}

    # Strip markdown code fences if the model wraps output in ```json ... ```
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```$", "", text).strip()

    try:
        parsed = json.loads(text)
        route_id = parsed.get("route_id")
        answer_text = parsed.get("text", "")

        # Ensure route_id is an int (or None)
        if route_id is not None:
            route_id = int(route_id)

        return {"route_id": route_id, "text": answer_text}

    except (json.JSONDecodeError, ValueError):
        # Fallback: return raw text with no route_id
        return {"route_id": None, "text": raw_text.strip()}


async def query_route_llm(message: str, user_id: int):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # ---- Fetch DB ----
        cursor.execute("SELECT * FROM multimodal_routes WHERE user_id = ?", (user_id,))
        multimodal_routes = [
            dict(zip([col[0] for col in cursor.description], row))
            for row in cursor.fetchall()
        ]

        # cleaned_multimodal_routes = []
        # for route in multimodal_routes:
        #     multimodal_data = route.get("multimodal_data")
        #     if isinstance(multimodal_data, str):
        #         multimodal_data = json.loads(multimodal_data)

        #     for seg_key in ["segment_1", "segment_2", "segment_3"]:
        #         segment = multimodal_data.get(seg_key)
        #         if isinstance(segment, dict):
        #             segment.pop("path", None)

        #     cleaned_multimodal_routes.append({
        #         "route_id": route.get("route_id"),
        #         "is_active": route.get("is_active"),
        #         "multimodal_data": multimodal_data
        #     })

        cursor.execute("SELECT * FROM persistent_routes WHERE user_id = ?", (user_id,))
        persistent_routes = [
            dict(zip([col[0] for col in cursor.description], row))
            for row in cursor.fetchall()
        ]

        cleaned_routes = []
        for route in persistent_routes:
            route_data = route.get("route_data")

            # Ensure route_data is a dict, not a raw JSON string
            if isinstance(route_data, str):
                route_data = json.loads(route_data)

            # Guard: only proceed if it's actually a dict
            if not isinstance(route_data, dict):
                continue

            if "optimal_routes" in route_data and isinstance(route_data["optimal_routes"], list):
                for opt_route in route_data["optimal_routes"]:
                    if isinstance(opt_route, dict):
                        opt_route.pop("path", None)

            if "alternative_route" in route_data and isinstance(route_data["alternative_route"], dict):
                route_data["alternative_route"].pop("path", None)

            cleaned_routes.append({
                "route_id": route.get("route_id"),
                "is_active": route.get("is_active"),
                "route_data": route_data
            })


        # Same guard for multimodal routes
        cleaned_multimodal_routes = []
        for route in multimodal_routes:
            multimodal_data = route.get("multimodal_data")

            if isinstance(multimodal_data, str):
                multimodal_data = json.loads(multimodal_data)

            if not isinstance(multimodal_data, dict):
                continue

            for seg_key in ["segment_1", "segment_2", "segment_3"]:
                segment = multimodal_data.get(seg_key)
                if isinstance(segment, dict):
                    segment.pop("path", None)

            cleaned_multimodal_routes.append({
                "route_id": route.get("route_id"),
                "is_active": route.get("is_active"),
                "multimodal_data": multimodal_data
            })
        db_dump = {
            "multimodal_routes": cleaned_multimodal_routes,
            "persistent_routes": cleaned_routes
        }

        # ---- Build Prompt ----
        user_prompt = f"""
DATABASE:
{json.dumps(db_dump)}

QUESTION:
{message}
"""

        # ---- LLM Call ----
        if client is None:
            raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")

        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5.2-2025-12-11",
            temperature=0.0,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
        )

        raw_answer = response.output_text
        parsed_answer = clean_llm_response(raw_answer)

        return {
            "status": True,
            "route_id": parsed_answer["route_id"],   # int or None
            "answer": parsed_answer["text"]
        }

    except Exception as e:
        import traceback
        traceback.print_exc()          # prints full stack trace to console
        return {"message": f"Unable to get details. Error: {str(e)}"}
    

# SYSTEM_PROMPT = """

# You are a deterministic route analysis assistant used in a professional logistics platform.

# You must strictly follow ALL rules below.

# ────────────────────────────────
# DATA AUTHORITY
# ────────────────────────────────

# - Use ONLY the data inside the DATABASE section.
# - The DATABASE is the complete and final source of truth.
# - Never invent routes, values, or assumptions.
# - If data is missing, clearly state that it is unavailable.
# - Never mention database structures or internal implementation.

# ────────────────────────────────
# ROUTE UNDERSTANDING
# ────────────────────────────────

# Routes may be:

# - Direct (single leg)
# - Road-only
# - Air-only
# - Multimodal (road + air + road)
# - Optimal routes
# - Alternative routes
# - Multi-segment routes

# All must be interpreted correctly.

# Airports are valid intermediate nodes.
# City ↔ Airport connections are continuous.
# Naming differences never break a valid transport chain.

# ────────────────────────────────
# TOTAL METRIC AUTHORITY RULE
# ────────────────────────────────

# If route-level totals exist (total_distance, total_distance_km,
# total_duration, total_cost):

# - ALWAYS use them for evaluation and comparison.
# - NEVER use segment-level values for ranking.
# - Segment values are for explanation only.
# - Route-level totals override ALL segment values.

# This rule applies to:
# - Multimodal routes
# - Road-only routes
# - Air-only routes
# - Direct routes
# - Cross-type comparisons

# Ranking decisions must use ONLY route-level totals.

# ────────────────────────────────
# COMPARISON & RANKING RULE
# ────────────────────────────────

# When users request:

# - Shortest → minimum total distance
# - Longest → maximum total distance
# - Fastest → minimum total duration
# - Slowest → maximum total duration
# - Cheapest → minimum total cost
# - Most expensive → maximum total cost
# - Any combination → satisfy ALL requested conditions

# You must:

# 1. Identify the correct metric(s).
# 2. Rank strictly using route-level totals only.
# 3. Select the single best route.

# Never select a second-best route
# if a better-ranked route satisfies the request.

# If multiple routes are equally ranked,
# select the first one provided in the database.

# Never optimize using a metric that is not available.

# ────────────────────────────────
# NUMERICAL MAX/MIN DETERMINATION RULE:
# ────────────────────────────────

# For any max/min request:

# Step 1 — Compile the COMPLETE list of all eligible
# routes and their total metric values.
# Step 2 — Identify the maximum or minimum value
# from that complete list.
# Step 3 — Match that value to its route.

# Step 1 is mandatory and non-skippable.
# A value is not confirmed as max/min until
# Steps 1, 2, and 3 are completed in order.

# ────────────────────────────────
# EXHAUSTIVE EVALUATION RULE:
# ────────────────────────────────

# You must evaluate every eligible route regardless
# of transport type (road, air, multimodal) in one
# unified comparison pass.

# You are NEVER allowed to:
# - Rank road routes separately from air routes.
# - Select a "best road" and "best air" winner first,
#   then compare those winners.
# - Stop evaluation before all routes are checked.

# Selection is only valid after every qualifying
# route's total metric has been compared in a
# single unified pass.

# Early stopping is forbidden in all cases, including
# when filtering by a single transport type (road-only,
# air-only, or multimodal).

# You must not treat any route as the winner until
# every route matching the filter has been checked.

# A large value encountered early in evaluation is
# NOT a confirmed maximum. The maximum is only
# confirmed after all eligible routes are evaluated.

# ────────────────────────────────
# STATELESS EVALUATION RULE:
# ────────────────────────────────

# Every query must be answered by evaluating the
# DATABASE from scratch.

# You must never reuse or recall an answer from
# earlier in the conversation as the basis for a
# new evaluation.

# Previous answers — including your own — are not
# data. Only the DATABASE is data.

# If a previous answer conflicts with a fresh
# evaluation of the DATABASE, the fresh evaluation
# wins. Always.

# ────────────────────────────────
# FLAT POOL RULE:
# ────────────────────────────────

# Before ranking, merge ALL eligible routes —
# road-only, air-only, and multimodal — into a
# single flat list. Never rank within transport-type
# subgroups first. Ranking applies to the merged list only.

# If two routes have equal total metric values,
# select the one that appears first in the database.
# Never use transport type as a tiebreaker.

# ────────────────────────────────
# SELF-CONSISTENCY CHECK RULE:
# ────────────────────────────────

# Before finalising any max/min answer, verify it
# by asking internally:

# "Is there any route in the eligible set whose
# total metric value exceeds (or is less than)
# the value I am about to state?"

# If yes, that route is the correct answer instead.
# You may not proceed until this check passes.

# If the check fails, discard the current answer,
# identify the correct route, and restart from Step 3
# of the NUMERICAL MAX/MIN DETERMINATION RULE.

# ────────────────────────────────
# TIME FORMAT RULE
# ────────────────────────────────

# Durations are in hours (may include decimals).

# Convert to:
# X hrs Y mins

# Do NOT display decimal hour values.

# Examples:
# 5 → 5 hrs 0 mins
# 5.5 → 5 hrs 30 mins
# 2.25 → 2 hrs 15 mins

# ────────────────────────────────
# INTENT RESPONSE LOGIC
# ────────────────────────────────

# - Summary request → concise overview.
# - Best/optimal request → focus on efficiency.
# - Time-focused request → emphasize duration.
# - Distance-focused request → emphasize distance.
# - “How it works” → explain segment flow.
# - General query → balanced explanation.

# Include only information relevant to user intent.

# ────────────────────────────────
# STYLE RULES
# ────────────────────────────────

# - Natural, professional tone.
# - No JSON.
# - No bullet lists.
# - No internal reasoning.
# - No repeated templates.
# - No unnecessary data dumping.

# ────────────────────────────────
# OUTPUT RESTRICTION RULE
# ────────────────────────────────

# Your final output must ONLY contain the final answer to the user's query.

# Never list all eligible routes.
# Never include intermediate evaluations, comparisons, or compiled lists.
# Never repeat or expose the ranking process.

# Only return the final selected route and the required explanation based on user intent.

# ────────────────────────────────
# FAILURE RULE
# ────────────────────────────────

# If no valid route exists:

# "There is no available route from <SOURCE> to <DESTINATION> based on the current data."

# """

# async def query_route_llm(message: str, user_id: int):

#     try:
#         # cursor = request.app.state.db.cursor()
#         conn = get_db_connection()
#         cursor = conn.cursor()

#         # ---- Fetch DB ----
#         cursor.execute("SELECT * FROM multimodal_routes WHERE user_id = ?", (user_id,))
#         multimodal_routes = [
#             dict(zip([col[0] for col in cursor.description], row))
#             for row in cursor.fetchall()
#         ]

#         cleaned_multimodal_routes = []

#         for route in multimodal_routes:
#             multimodal_data = route.get("multimodal_data")

#             # Parse JSON if stored as string
#             if isinstance(multimodal_data, str):
#                 multimodal_data = json.loads(multimodal_data)

#             # Extract segments
#             for seg_key in ["segment_1", "segment_2", "segment_3"]:
#                 segment = multimodal_data.get(seg_key)

#                 if isinstance(segment, dict):
#                     # Remove path if exists
#                     segment.pop("path", None)

#             cleaned_multimodal_routes.append({
#                 "route_id": route.get("route_id"),
#                 "is_active": route.get("is_active"),
#                 "multimodal_data": multimodal_data
#             })

        

#         cursor.execute("SELECT * FROM persistent_routes WHERE user_id = ?", (user_id,))
#         persistent_routes = [
#             dict(zip([col[0] for col in cursor.description], row))
#             for row in cursor.fetchall()
#         ]

#         cleaned_routes = []

#         for route in persistent_routes:
#             route_data = route.get("route_data")
            
#             # Parse JSON if stored as string
#             if isinstance(route_data, str):
#                 route_data = json.loads(route_data)

#             # Case 1: final_result style with optimal_routes
#             if "optimal_routes" in route_data and isinstance(route_data["optimal_routes"], list):
#                 for opt_route in route_data["optimal_routes"]:
#                     if isinstance(opt_route, dict):
#                         opt_route.pop("path", None)

#             # Case 2: alternative route style
#             if "alternative_route" in route_data and isinstance(route_data["alternative_route"], dict):
#                 route_data["alternative_route"].pop("path", None)

#             # Add cleaned route back
#             cleaned_routes.append({
#                 "route_id": route.get("route_id"),
#                 "is_active": route.get("is_active"),
#                 "route_data": route_data
#             })

#         db_dump = {

#             "multimodal_routes": cleaned_multimodal_routes,
#             "persistent_routes": cleaned_routes
#         }

#         # print(f"==>> db_dump:  {db_dump}")
#         # ---- Build Prompt ----
#         user_prompt = f"""
# DATABASE:
# {json.dumps(db_dump)}

# QUESTION:
# {message}
# """
#         # print(f"==>> user_prompt:  {user_prompt}")

#         messages=[
#                 {"role": "system", "content": SYSTEM_PROMPT},
#                 {"role": "user", "content": user_prompt}
#         ]
#         print(f"==>> messages before LLM call:  {messages}")
#         # ---- LLM Call ----
#         response = await asyncio.to_thread(
#             client.responses.create,
#             model="gpt-5.2-2025-12-11",
#             temperature=0.0,
#             input=[
#                 {"role": "system", "content": SYSTEM_PROMPT},
#                 {"role": "user", "content": user_prompt}
#             ]
#         )

#         raw_answer = response.output_text

#         clean_answer = clean_llm_response(raw_answer)

#         print(clean_answer)


#         return {
#             "status": True,
#             "answer": clean_answer
#         }

#     except Exception as e:
#         return {"message": "Unable to get details."}
    

# def clean_llm_response(raw_text: str) -> str:

#     if not raw_text:
#         return ""

#     text = raw_text.replace("\\n", "\n")

#     text = text.replace("**", "").replace("`", "").strip()

#     lines = text.split("\n")
#     clean_lines = []
#     for line in lines:
#         line = line.strip()
#         if line.startswith("- "):

#             line = line[2:].strip()
#             clean_lines.append(line + ".")
#         elif line:
#             clean_lines.append(line)

#     final_clean_text = " ".join(clean_lines)
#     return final_clean_text


# ======================================================= API ======================================================

@router.post("/llm/query-route")
async def llm_query_route(payload: RouteQueryRequest, current_user = Depends(get_current_user)):
    
    user_id = current_user.get("user_id")
        
    if not user_id:
        return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
        
    message = payload.question
    result = await query_route_llm(message, user_id)
    return result
