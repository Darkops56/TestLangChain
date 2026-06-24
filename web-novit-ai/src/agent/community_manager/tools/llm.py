"""LLM factory — Azure AI Foundry via LiteLLM.

LangGraph/LangChain doesn't support Azure AI Foundry natively.
We use LiteLLM as a lightweight proxy that translates LangChain's
ChatOpenAI calls into Azure-compatible requests.

References:
  - https://docs.litellm.ai/docs/providers/azure
  - https://learn.microsoft.com/en-us/azure/ai-studio/
"""

from __future__ import annotations

import logging
import os
from urllib.parse import parse_qs, urlparse

from langchain_openai import AzureChatOpenAI, ChatOpenAI

from community_manager.config.settings import get_settings

logger = logging.getLogger(__name__)


def _parse_legacy_foundry_deployment_url() -> tuple[str | None, str | None, str | None, str | None]:
    """Extract endpoint, key, deployment and API version from the shared .NET env vars.

    The deployed server already has ``AIFoundryDeployment`` and ``AIFoundryKey`` wired
    for the .NET backend. Reusing them lets the Python agent work without adding a new
    set of production secrets.
    """
    deployment_url = os.getenv("AIFoundryDeployment", "").strip()
    api_key = os.getenv("AIFoundryKey", "").strip()
    if not deployment_url or not api_key:
        return None, None, None, None

    parsed = urlparse(deployment_url)
    endpoint = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
    query = parse_qs(parsed.query)
    api_version = query.get("api-version", [None])[0]

    deployment = None
    path_parts = [part for part in parsed.path.split("/") if part]
    if "deployments" in path_parts:
        index = path_parts.index("deployments")
        if index + 1 < len(path_parts):
            deployment = path_parts[index + 1]

    return endpoint, api_key, deployment, api_version


def _build_azure_chat(
    deployment: str,
    *,
    endpoint: str | None = None,
    api_key: str | None = None,
    api_version: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> AzureChatOpenAI:
    """Create an Azure chat client for deployment-based chat/completions endpoints."""
    settings = get_settings()
    legacy_endpoint, legacy_api_key, legacy_deployment, legacy_api_version = _parse_legacy_foundry_deployment_url()

    use_legacy_config = not settings.azure_foundry_llm_endpoint and not settings.azure_foundry_llm_api_key
    _deployment = deployment
    _endpoint = endpoint or settings.azure_foundry_llm_endpoint
    _api_key = api_key or settings.azure_foundry_llm_api_key
    _api_version = api_version or settings.azure_foundry_llm_api_version

    if use_legacy_config:
        # Only use legacy config for values that weren't explicitly provided
        _endpoint = _endpoint or legacy_endpoint
        _api_key = _api_key or legacy_api_key
        _api_version = _api_version or legacy_api_version
        # IMPORTANT: do NOT override deployment if already explicitly set
        _deployment = _deployment or legacy_deployment

    return AzureChatOpenAI(
        azure_endpoint=_endpoint,
        azure_deployment=_deployment,
        openai_api_key=_api_key,
        openai_api_version=_api_version,
        temperature=temperature,
        max_tokens=max_tokens,
    )


# ── Pre-built LLM accessors ────────────────────────────────────

def get_main_llm(temperature: float = 0.7) -> ChatOpenAI:
    """Primary LLM (GPT-4o or equivalent) — used by Strategist, Copywriter, Designer."""
    settings = get_settings()
    logger.debug("Building main LLM: %s", settings.azure_foundry_llm_deployment)
    return _build_azure_chat(
        deployment=settings.azure_foundry_llm_deployment,
        temperature=temperature,
    )


def get_small_llm(temperature: float = 0.3) -> ChatOpenAI:
    """Smaller/cheaper LLM (GPT-4o-mini) — used by Evaluator."""
    settings = get_settings()
    logger.debug("Building small LLM: %s", settings.azure_foundry_llm_small_deployment)
    return _build_azure_chat(
        deployment=settings.azure_foundry_llm_small_deployment,
        temperature=temperature,
    )


def get_responder_llm(temperature: float = 0.5) -> ChatOpenAI:
    """Cheap LLM route for inbound Instagram/Facebook replies and comments."""
    settings = get_settings()
    logger.debug("Building responder LLM: %s", settings.resolved_responder_llm_deployment)
    return _build_azure_chat(
        deployment=settings.resolved_responder_llm_deployment,
        temperature=temperature,
        max_tokens=500,
    )


def get_creative_llm(temperature: float = 0.9) -> ChatOpenAI:
    """High-creativity LLM — used by Copywriter for more creative copy."""
    settings = get_settings()
    return _build_azure_chat(
        deployment=settings.azure_foundry_llm_deployment,
        temperature=temperature,
        max_tokens=3000,
    )


def get_newsletter_llm(temperature: float = 1.0, max_tokens: int = 4000) -> ChatOpenAI:
    """Newsletter LLM (GPT-5.4) on a separate Azure endpoint.

    Used by the nurturing workflow for newsletter generation/revision.
    The temperature defaults to 1.0 because GPT-5.4-chat only supports
    temperature=1 (per the C# implementation comment).
    """
    settings = get_settings()
    if not settings.is_nurturing_configured:
        raise RuntimeError(
            "Newsletter AI not configured — set NURTURING_NEWSLETTER_ENDPOINT, "
            "NURTURING_NEWSLETTER_DEPLOYMENT, and NURTURING_NEWSLETTER_KEY."
        )
    logger.debug(
        "Building newsletter LLM: %s @ %s (max_tokens=%d)",
        settings.nurturing_newsletter_deployment,
        settings.nurturing_newsletter_endpoint,
        max_tokens,
    )
    return _build_azure_chat(
        deployment=settings.nurturing_newsletter_deployment,
        endpoint=settings.nurturing_newsletter_endpoint,
        api_key=settings.nurturing_newsletter_key,
        api_version=settings.nurturing_newsletter_api_version,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_reply_llm(temperature: float = 0.7) -> ChatOpenAI:
    """LLM for lead reply generation — uses the main (cheap) model.

    Mirrors the C# ``CallReplyAIPlainAsync`` which uses the standard
    AI Foundry deployment (same as the web chatbot).
    """
    settings = get_settings()
    logger.debug("Building reply LLM: %s", settings.azure_foundry_llm_deployment)
    return _build_azure_chat(
        deployment=settings.azure_foundry_llm_deployment,
        temperature=temperature,
        max_tokens=800,
    )


def get_closing_llm(temperature: float = 0.8) -> ChatOpenAI:
    """LLM for personal closing generation — uses the main (cheap) model.

    Mirrors the C# ``GeneratePersonalClosingAsync`` which uses GPT-4o
    with a low max_tokens for short closings.
    """
    settings = get_settings()
    return _build_azure_chat(
        deployment=settings.azure_foundry_llm_deployment,
        temperature=temperature,
        max_tokens=100,
    )
