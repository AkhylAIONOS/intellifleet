"""LLM provider construction. Secrets never leave this module."""

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from langchain_openai import ChatOpenAI

from backend.config.config import settings


class LLMConfigurationError(RuntimeError):
    pass


class AzureFoundryResponsesChatOpenAI(ChatOpenAI):
    """Compatibility adapter for Foundry deployments requiring string input.

    The project Responses endpoint rejects the untyped multi-message objects
    produced by this LangChain version. A labelled transcript is accepted as a
    single Responses input string and preserves the conversation roles.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        items = payload.get("input")
        if isinstance(items, list):
            transcript = []
            for item in items:
                if not isinstance(item, dict):
                    transcript.append(str(item))
                    continue
                role = str(item.get("role") or "user").upper()
                content = item.get("content", "")
                if isinstance(content, list):
                    content = "\n".join(
                        str(part.get("text", "")) if isinstance(part, dict) else str(part)
                        for part in content
                    )
                transcript.append(f"[{role}]\n{content}")
            payload["input"] = "\n\n".join(transcript)
        return payload


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    deployment: str | None
    configured: bool
    error_code: str | None = None
    message: str | None = None


def _azure_endpoint(value: str) -> str:
    """Return the Azure resource endpoint without duplicating OpenAI paths."""
    parsed = urlsplit(value.strip().rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LLMConfigurationError("AZURE_AI_ENDPOINT is invalid.")
    path = parsed.path
    marker = path.lower().find("/openai/")
    if marker >= 0:
        path = path[:marker]
    elif path.lower().endswith("/openai"):
        path = path[:-7]
    return urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))


def provider_status() -> ProviderStatus:
    provider = (settings.AI_PROVIDER or "openai").strip().lower()
    if provider == "azure":
        missing = [name for name, value in (
            ("AZURE_AI_ENDPOINT", settings.AZURE_AI_ENDPOINT),
            ("AZURE_AI_API_KEY", settings.AZURE_AI_API_KEY),
            ("AZURE_AI_DEPLOYMENT", settings.AZURE_AI_DEPLOYMENT),
        ) if not value]
        if missing:
            code = f"{missing[0]}_MISSING"
            return ProviderStatus(provider, settings.AZURE_AI_DEPLOYMENT, False, code,
                                  f"AI chat is unavailable because {', '.join(missing)} is missing.")
        return ProviderStatus(provider, settings.AZURE_AI_DEPLOYMENT, True)
    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            return ProviderStatus(provider, None, False, "OPENAI_API_KEY_MISSING",
                                  "AI chat is unavailable because OPENAI_API_KEY is missing.")
        return ProviderStatus(provider, "gpt-5.2-2025-12-11", True)
    return ProviderStatus(provider, None, False, "AI_PROVIDER_UNSUPPORTED",
                          f"AI chat is unavailable because AI_PROVIDER '{provider}' is unsupported.")


def create_chat_model():
    status = provider_status()
    if not status.configured:
        raise LLMConfigurationError(status.message or "LLM configuration is incomplete.")
    if status.provider == "azure":
        endpoint = _azure_endpoint(settings.AZURE_AI_ENDPOINT)
        return AzureFoundryResponsesChatOpenAI(
            base_url=f"{endpoint}/openai/v1/",
            api_key=settings.AZURE_AI_API_KEY,
            model=settings.AZURE_AI_DEPLOYMENT,
            use_responses_api=True,
            max_retries=2,
        )
    return ChatOpenAI(model=status.deployment, api_key=settings.OPENAI_API_KEY, temperature=0)
