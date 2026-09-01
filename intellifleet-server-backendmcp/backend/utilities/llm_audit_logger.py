import os
from datetime import datetime
from typing import List, Dict, Any

LOG_DIR = "logs/llm_audit"

os.makedirs(LOG_DIR, exist_ok=True)


def save_llm_audit_log(
    user_id: int,
    user_message: str,
    final_response: str,
    tools_used: List[str],
    token_usage: Dict[str, Any] | None = None,
):
    """
    Saves LLM interaction details into a text file.
    """

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    filename = f"{LOG_DIR}/user_{user_id}.txt"

    log_entry = f"""
================================================================================
Timestamp       : {timestamp}
User ID         : {user_id}

USER INPUT:
{user_message}

TOOLS USED:
{", ".join(tools_used) if tools_used else "None"}

TOKEN USAGE:
{token_usage if token_usage else "Not Available"}

LLM RESPONSE:
{final_response}
================================================================================
"""

    with open(filename, "a", encoding="utf-8") as f:
        f.write(log_entry)


        