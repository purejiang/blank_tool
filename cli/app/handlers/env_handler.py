#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Environment descriptor CRUD and override handlers (T15).

Provides ``env.list``, ``env.add``, ``env.delete``, ``env.set_custom``,
and ``env.reset_custom`` JSON-RPC methods.  Descriptors are validated via
:class:`~app.env.descriptor.EnvironmentDescriptor.from_dict` and
persisted to the T14 writable overlay under
``<output_dir>/registry/environments/``.  Bundled environments
(``cli/registry/environments/``) are protected from deletion.

Environment overrides (custom env-vars, paths) are persisted alongside
tool custom paths in ``<output_dir>/registry/overrides.json`` under
an ``env_overrides`` key (tolerant of missing sections).
"""

from app.env.registry import get_env_registry
from app.env.descriptor import EnvironmentDescriptor
from app.env.overrides_store import OverridesStore
from app.utils.logger import Logger

logger = Logger.get_logger("EnvHandler")


# ── Handlers ───────────────────────────────────────────────────────────


def handle_env_list(params, stream_handler):
    """List every resolved environment from the :class:`EnvironmentRegistry`."""
    registry = get_env_registry()
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
        registry = get_env_registry()
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
        registry = get_env_registry()
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

    store = OverridesStore()
    data = store.load()
    env_overrides = data.get("env_overrides")
    if not isinstance(env_overrides, dict):
        env_overrides = {}
    env_overrides[name] = dict(overrides)
    data["env_overrides"] = env_overrides
    store.save(data)

    return {"set": name, "overrides": dict(overrides)}


def handle_env_reset_custom(params, stream_handler):
    """Remove the environment override dict for *name*.

    Expects ``params.name``.  No-op when no override existed.
    """
    name = params.get("name", "")
    if not name:
        return {"error": "Missing 'name' field"}

    store = OverridesStore()
    data = store.load()
    env_overrides = data.get("env_overrides")
    if isinstance(env_overrides, dict):
        env_overrides.pop(name, None)
        data["env_overrides"] = env_overrides
        store.save(data)

    return {"reset": name}


API_MAP = {
    "env.list": handle_env_list,
    "env.add": handle_env_add,
    "env.delete": handle_env_delete,
    "env.set_custom": handle_env_set_custom,
    "env.reset_custom": handle_env_reset_custom,
}
