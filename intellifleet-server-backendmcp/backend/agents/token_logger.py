# backend/agents/token_logger.py

import os
from datetime import datetime

LOG_FILE = os.path.join(os.path.dirname(__file__), "token_usage.txt")


def _extract_tokens(response) -> dict:
    """Extract input/output token counts from a LangChain LLM response."""
    # Newer LangChain versions expose usage_metadata
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        meta = response.usage_metadata
        return {
            "input_tokens": meta.get("input_tokens", 0),
            "output_tokens": meta.get("output_tokens", 0),
            "total_tokens": meta.get("total_tokens", 0),
        }
    # Older versions expose it via response_metadata
    if hasattr(response, "response_metadata") and response.response_metadata:
        usage = response.response_metadata.get("token_usage", {})
        return {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def log_token_usage(call_name: str, user_id: int, response):
    """Log token usage for one LLM call to token_usage.txt."""
    tokens = _extract_tokens(response)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    line = (
        f"[{timestamp}] "
        f"user_id={user_id} | "
        f"call={call_name} | "
        f"input_tokens={tokens['input_tokens']} | "
        f"output_tokens={tokens['output_tokens']} | "
        f"total_tokens={tokens['total_tokens']}\n"
    )

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
