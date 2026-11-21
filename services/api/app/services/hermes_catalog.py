"""Read-only, bounded discovery of the pinned Hermes catalogs.

This adapter never loads, installs, edits, or executes a skill. Catalog metadata
is untrusted upstream text and is returned only as inert, size-limited JSON.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings


class HermesCatalogUnavailable(RuntimeError):
    """Raised when the isolated Hermes catalog is not configured."""


class HermesCatalogError(RuntimeError):
    """Raised for safe, non-sensitive catalog failures."""


_MAX_RESPONSE_BYTES = 256 * 1024
_MAX_SKILLS = 500
_MAX_TOOLSETS = 100
_MAX_TOOLS_PER_SET = 100
_NAME_MAX = 120
_DESCRIPTION_MAX = 1000
_CATEGORY_MAX = 80
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _safe_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return _CONTROL_CHARS.sub(" ", value).strip()[:limit]


def _catalog_base_url(value: object) -> str:
    if not isinstance(value, str):
        raise HermesCatalogUnavailable("Hermes catalog is not configured.")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise HermesCatalogUnavailable("Hermes catalog URL is invalid.") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise HermesCatalogUnavailable("Hermes catalog URL is invalid.")
    return value.rstrip("/")


def _normalize_skill_catalog(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or payload.get("object") != "list":
        raise HermesCatalogError("Hermes returned an invalid skill catalog.")
    data = payload.get("data")
    if not isinstance(data, list) or len(data) > _MAX_SKILLS:
        raise HermesCatalogError("Hermes returned an invalid skill catalog.")
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in data:
        if not isinstance(raw, dict):
            continue
        name = _safe_text(raw.get("name"), _NAME_MAX)
        if (
            not name
            or name.startswith("/")
            or chr(92) in name
            or any(part == ".." for part in name.split("/"))
            or name.casefold() in seen
        ):
            continue
        seen.add(name.casefold())
        items.append({
            "name": name,
            "description": _safe_text(raw.get("description"), _DESCRIPTION_MAX),
            "category": _safe_text(raw.get("category"), _CATEGORY_MAX),
        })
    return {"source": "hermes-upstream", "items": items, "count": len(items)}


def _normalize_toolset_catalog(payload: object) -> dict[str, object]:
    if (
        not isinstance(payload, dict)
        or payload.get("object") != "list"
        or payload.get("platform") != "api_server"
    ):
        raise HermesCatalogError("Hermes returned an invalid toolset catalog.")
    data = payload.get("data")
    if not isinstance(data, list) or len(data) > _MAX_TOOLSETS:
        raise HermesCatalogError("Hermes returned an invalid toolset catalog.")
    items: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in data:
        if not isinstance(raw, dict):
            continue
        name = _safe_text(raw.get("name"), 80)
        enabled = raw.get("enabled")
        raw_tools = raw.get("tools")
        if (
            not name
            or name.casefold() in seen
            or not isinstance(enabled, bool)
            or not isinstance(raw_tools, list)
            or len(raw_tools) > _MAX_TOOLS_PER_SET
        ):
            continue
        tools = sorted({
            item for item in raw_tools
            if isinstance(item, str) and _TOOL_NAME.fullmatch(item)
        })
        seen.add(name.casefold())
        items.append({
            "name": name,
            "label": _safe_text(raw.get("label"), 100),
            "description": _safe_text(raw.get("description"), 500),
            "enabled": enabled,
            "tools": tools,
        })
    return {"source": "hermes-upstream", "items": items, "count": len(items)}


async def _fetch_catalog_payload(path: str) -> object:
    """Fetch one fixed metadata route; no caller-controlled URL or path is accepted."""
    settings = get_settings()
    if not settings.hermes_agent_enabled or not settings.hermes_agent_isolation_confirmed:
        raise HermesCatalogUnavailable("Hermes catalog is disabled.")
    if not settings.hermes_agent_api_key:
        raise HermesCatalogUnavailable("Hermes catalog is not configured.")

    base_url = _catalog_base_url(settings.hermes_agent_base_url)
    token = settings.hermes_agent_api_key.get_secret_value()
    timeout = httpx.Timeout(8.0, connect=3.0)
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            async with client.stream(
                "GET",
                f"{base_url}{path}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            ) as response:
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared is not None:
                    try:
                        if int(declared) > _MAX_RESPONSE_BYTES:
                            raise HermesCatalogError("Hermes catalog is too large.")
                    except ValueError as exc:
                        raise HermesCatalogError("Hermes returned an invalid catalog.") from exc
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        raise HermesCatalogError("Hermes catalog is too large.")
                    chunks.append(chunk)
        return json.loads(b"".join(chunks).decode("utf-8"))
    except HermesCatalogError:
        raise
    except (httpx.HTTPError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        # Never return upstream response bodies, headers, or exception details.
        raise HermesCatalogError("Hermes catalog request failed.") from exc


async def get_hermes_skill_catalog() -> dict[str, object]:
    """Return only installed skill name/description/category metadata."""
    return _normalize_skill_catalog(await _fetch_catalog_payload("/v1/skills"))


async def get_hermes_toolset_catalog() -> dict[str, object]:
    """Return toolset metadata without configuration details or execution controls."""
    return _normalize_toolset_catalog(await _fetch_catalog_payload("/v1/toolsets"))
