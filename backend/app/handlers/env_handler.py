#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Environment descriptor CRUD and override handlers (T15).

Provides ``env.list``, ``env.add``, ``env.delete``, ``env.set_custom``,
and ``env.reset_custom`` JSON-RPC methods.  Descriptors are validated via
:class:`~app.env.descriptor.EnvironmentDescriptor.from_dict` and
persisted to the T14 writable overlay under
``<output_dir>/registry/environments/``.  Bundled environments
(``backend/registry/environments/``) are protected from deletion.

Environment overrides (custom env-vars, paths) are persisted alongside
tool custom paths in ``<output_dir>/registry/overrides.json`` under
an ``env_overrides`` key (tolerant of missing sections).
"""

import json
import os
from pathlib import Path
from typing import Optional

from app.env.registry import EnvironmentRegistry
from app.env.descriptor import EnvironmentDescriptor
from app.utils.env import get_output_dir
from app.utils.logger import Logger

logger = Logger.get_logger("EnvHandler")

# ── Singleton registry ────────────────────────────────────────────────

_env_registry: Optional[EnvironmentRegistry] = None


def _get_registry() -> EnvironmentRegistry:
    """Return the process-wide :class:`EnvironmentRegistry`, discovering
    with the writable overlay on first use."""
    global _env_registry
    if _env_registry is None:
        overlay = os.path.join(get_output_dir(), "registry")
        _env_registry = EnvironmentRegistry(overlay_dir=overlay)
        _env_registry.discover()
    return _env_registry


def _get_overlay_dir() -> str:
    """Return the writable overlay root (``<output>/registry``)."""
    return os.path.join(get_output_dir(), "registry")


# ── Override helpers ───────────────────────────────────────────────────

def _overrides_path() -> Path:
    return Path(_get_overlay_dir()) / "overrides.json"


def _load_env_overrides() -> dict:
    """Load the ``env_overrides`` section of overrides.json."""
    path = _overrides_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    env_ov = data.get("env_overrides")
    if isinstance(env_ov, dict):
        return {str(k): dict(v) for k, v in env_ov.items() if isinstance(v, dict)}
    return {}


def _save_env_overrides(overrides: dict) -> None:
    """Write the ``env_overrides`` section, preserving other sections."""
    path = _overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    if not isinstance(existing, dict):
        existing = {}

    existing["env_overrides"] = overrides
    path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Handlers ───────────────────────────────────────────────────────────


def handle_env_list(params, stream_handler):
    """List every resolved environment from the :class:`EnvironmentRegistry`."""
    registry = _get_registry()
    envs = registry.list_all()
    return {
        "environments": [
            {
                "name": env.name,
                "is_valid": env.is_valid,
                "binary_path": env.binary_path,
                "version": env.version,
                "root_path": env.root_path,
            }
            for env in envs
        ]
    }


def handle_env_add(params, stream_handler):
    """Validate and persist a new environment descriptor to the overlay.

    Expects ``params.descriptor`` as a dict conforming to
    :class:`EnvironmentDescriptor`.  Returns the descriptor name on
    success, or an ``error`` key on validation failure.
    """
    descriptor_data = params.get("descriptor")
    if not isinstance(descriptor_data, dict):
        return {"error": "Missing or invalid 'descriptor' field"}

    try:
        registry = _get_registry()
        descriptor = registry.add_descriptor(
            descriptor_data.get("name", ""), descriptor_data,
        )
        return {
            "name": descriptor.name,
            "display_name": descriptor.display_name,
            "type": descriptor.type,
        }
    except (ValueError, OSError) as exc:
        return {"error": str(exc)}


def handle_env_delete(params, stream_handler):
    """Remove an overlay environment descriptor by name.

    Bundled (non-overlay) environments are refused with a clean error.
    """
    name = params.get("name", "")
    if not name:
        return {"error": "Missing 'name' field"}

    try:
        registry = _get_registry()
        registry.delete_descriptor(name)
        return {"deleted": name}
    except (ValueError, OSError) as exc:
        return {"error": str(exc)}


def handle_env_set_custom(params, stream_handler):
    """Persist an environment override dict for *name*.

    Expects ``params.name`` and ``params.overrides`` (a free-form dict).
    Overrides are stored in ``overrides.json`` under ``env_overrides``.
    """
    name = params.get("name", "")
    overrides = params.get("overrides")
    if not name:
        return {"error": "Missing 'name' field"}
    if not isinstance(overrides, dict):
        return {"error": "Missing or invalid 'overrides' field"}

    all_overrides = _load_env_overrides()
    all_overrides[name] = dict(overrides)
    _save_env_overrides(all_overrides)

    return {"set": name, "overrides": dict(overrides)}


def handle_env_reset_custom(params, stream_handler):
    """Remove the environment override dict for *name*.

    Expects ``params.name``.  No-op when no override existed.
    """
    name = params.get("name", "")
    if not name:
        return {"error": "Missing 'name' field"}

    all_overrides = _load_env_overrides()
    all_overrides.pop(name, None)
    _save_env_overrides(all_overrides)

    return {"reset": name}


API_MAP = {
    "env.list": handle_env_list,
    "env.add": handle_env_add,
    "env.delete": handle_env_delete,
    "env.set_custom": handle_env_set_custom,
    "env.reset_custom": handle_env_reset_custom,
}
