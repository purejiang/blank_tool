#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Environment descriptor CRUD handlers (T15).

Provides ``env.list``, ``env.add``, and ``env.delete`` JSON-RPC methods.
Descriptors are validated via
:class:`~app.env.descriptor.EnvironmentDescriptor.from_dict` and persisted
to the T14 writable overlay under ``<output_dir>/registry/environments/``.
Bundled environments (``cli/registry/environments/``) are protected from
deletion.
"""

from app.env.registry import get_env_registry
from app.env.descriptor import EnvironmentDescriptor
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


API_MAP = {
    "env.list": handle_env_list,
    "env.add": handle_env_add,
    "env.delete": handle_env_delete,
}
