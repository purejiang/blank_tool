#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Environment descriptor CRUD handlers (T15).

Provides ``env.list``, ``env.add``, ``env.delete``, ``env.set_path`` and
``env.reset_path`` JSON-RPC methods.  Descriptors are validated via
:class:`~app.env.descriptor.EnvironmentDescriptor.from_dict` and persisted
to the T14 writable overlay under ``<output_dir>/registry/environments/``.
Bundled environments (``cli/registry/environments/``) are protected from
deletion.

Per-environment path overrides (WP3 #13) live under the ``env_paths`` key of
``<output_dir>/registry/overrides.json`` and take effect after
``registry.refresh()``.
"""

from app.env.registry import get_env_registry
from app.env.descriptor import EnvironmentDescriptor
from app.common.exceptions import ToolException
from app.utils.logger import Logger

logger = Logger.get_logger("EnvHandler")


# ── Shared serialization ───────────────────────────────────────────────


def serialize_environment(registry, env, path_overrides=None) -> dict:
    """Build the ``env.list`` entry for one resolved environment.

    ``workflow.list_envs`` reuses this so both methods stay interchangeable
    (docs/08).

    Args:
        registry: the :class:`EnvironmentRegistry` that resolved *env*.
        env: a :class:`~app.env.registry.ResolvedEnvironment`.
        path_overrides: pre-loaded ``registry.get_path_overrides()`` result
            (avoids re-reading the overrides file per entry).
    """
    descriptor = registry.get_descriptor(env.name)
    if path_overrides is None:
        path_overrides = registry.get_path_overrides()
    return {
        "name": env.name,
        "is_valid": env.is_valid,
        "binary_path": env.binary_path,
        "version": env.version,
        "root_path": env.root_path,
        "display_name": getattr(descriptor, "display_name", "") or "",
        "type": getattr(descriptor, "type", "") or "",
        "env_var_override": getattr(descriptor, "env_var_override", None) or "",
        "path_override": path_overrides.get(env.name, "") or "",
        "source": "overlay" if registry.is_overlay_descriptor(env.name) else "bundled",
    }


def _require_known_environment(registry, name: str) -> None:
    """Raise :class:`ToolException` when *name* is not a discovered environment."""
    if registry.get_descriptor(name) is None:
        raise ToolException(f"Unknown environment {name!r}")


# ── Handlers ───────────────────────────────────────────────────────────


def handle_env_list(params, stream_handler):
    """List every resolved environment from the :class:`EnvironmentRegistry`."""
    registry = get_env_registry()
    overrides = registry.get_path_overrides()
    return {
        "environments": [
            serialize_environment(registry, env, overrides)
            for env in registry.list_all()
        ]
    }


def handle_env_add(params, stream_handler):
    """Validate and persist a new environment descriptor to the overlay.

    Expects ``params.descriptor`` as a dict conforming to
    :class:`EnvironmentDescriptor`.  Returns the descriptor name on
    success.

    Raises:
        ToolException: on a missing/invalid ``descriptor`` or when the
            descriptor fails validation / the overlay cannot be written
            (WP0 #7: previously returned ``{"error": ...}`` as a success
            payload, which made callers mistake failures for successes).
    """
    descriptor_data = params.get("descriptor")
    if not isinstance(descriptor_data, dict):
        raise ToolException("Missing or invalid 'descriptor' field")

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
        raise ToolException(str(exc)) from exc


def handle_env_delete(params, stream_handler):
    """Remove an overlay environment descriptor by name.

    Bundled (non-overlay) environments are refused.

    Raises:
        ToolException: on a missing ``name``, or when *name* has no overlay
            descriptor (bundled environments are protected).
    """
    name = params.get("name", "")
    if not name:
        raise ToolException("Missing 'name' field")

    try:
        registry = get_env_registry()
        registry.delete_descriptor(name)
        return {"deleted": name}
    except (ValueError, OSError) as exc:
        raise ToolException(str(exc)) from exc


def handle_env_set_path(params, stream_handler):
    """Persist a per-environment path override (WP3 #13).

    ``path`` is either the binary itself or a directory probed like a runtime
    root.  The resolution cache is dropped afterwards, so the new override is
    visible immediately.

    Returns:
        The updated environment entry (same shape as ``env.list`` entries).

    Raises:
        ToolException: on a missing ``name``/``path`` or an unknown environment.
    """
    name = params.get("name", "")
    if not isinstance(name, str) or not name:
        raise ToolException("Missing 'name' field")
    path = params.get("path")
    if not isinstance(path, str) or not path:
        raise ToolException("Missing 'path' field")

    registry = get_env_registry()
    _require_known_environment(registry, name)

    registry.set_path_override(name, path)
    registry.refresh()  # resolution cache must not outlive the override
    return serialize_environment(registry, registry.resolve(name))


def handle_env_reset_path(params, stream_handler):
    """Drop the per-environment path override and return the updated entry.

    Raises:
        ToolException: on a missing ``name`` or an unknown environment.
    """
    name = params.get("name", "")
    if not isinstance(name, str) or not name:
        raise ToolException("Missing 'name' field")

    registry = get_env_registry()
    _require_known_environment(registry, name)

    registry.reset_path_override(name)
    registry.refresh()
    return serialize_environment(registry, registry.resolve(name))


API_MAP = {
    "env.list": handle_env_list,
    "env.add": handle_env_add,
    "env.delete": handle_env_delete,
    "env.set_path": handle_env_set_path,
    "env.reset_path": handle_env_reset_path,
}
