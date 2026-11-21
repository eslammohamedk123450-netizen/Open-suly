"""Read-only, bounded discovery of the pinned Hermes skill catalog.

This adapter never loads, installs, edits, or executes a skill. Skill metadata is
untrusted upstream text and is returned only as inert, size-limited JSON.
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
_NAME_MAX = 120
_DESCRIPTION_MAX = 1000
_CATEGORY_MAX = 80
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


async def get_hermes_skill_catalog() -> dict[str, object]:
    """Fetch only the upstream skill name/description/category listing.

    Both feature and isolation gates must be explicitly enabled. The isolation
    flag remains an operator assertion; this read-only endpoint does not prove
    or create a sandbox and cannot be used to enable task execution.
    """
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
                f"{base_url}/v1/skills",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            ) as response:
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared is not None:
                    try:
                        if int(declared) > _MAX_RESPONSE_BYTES:
                            raise HermesCatalogError("Hermes skill catalog is too large.")
                    except ValueError:
                        raise HermesCatalogError("Hermes returned an invalid skill catalog.")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        raise HermesCatalogError("Hermes skill catalog is too large.")
                    chunks.append(chunk)
        payload = json.loads(b"".join(chunks).decode("utf-8"))
        return _normalize_skill_catalog(payload)
    except HermesCatalogError:
        raise
    except (httpx.HTTPError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        # Never return upstream response bodies, headers, or exception details.
        raise HermesCatalogError("Hermes skill catalog request failed.") from exc
