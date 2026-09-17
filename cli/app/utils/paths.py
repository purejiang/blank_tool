import os

# Leaf module: pure path helpers shared by ``app.env`` and
# ``app.env.registry``. Imports nothing from the rest of the app, so it can
# never participate in an import cycle. Previously ``resolve_path`` and
# ``get_runtime_dir`` were duplicated across modules (each worked around an
# import cycle with a local copy and a "keep in sync" comment); they now live
# here as the single source of truth.

# Backend root directory (absolute path). paths.py lives at cli/app/utils/,
# so two parents up lands on cli/.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def resolve_path(path_str: str) -> str:
    """
    Resolve a path string to an absolute path.
    If the path is relative, it is resolved relative to the cli root.
    """
    if not path_str:
        return ""

    # If absolute, return as is
    if os.path.isabs(path_str):
        return path_str

    # Resolve relative to root
    return os.path.normpath(os.path.join(ROOT, path_str))


def get_runtime_dir() -> str:
    """
    Get the runtime directory.

    Priority: ``BT_RUNTIME_DIR`` env var (resolved against cli/), then
    ``cli/runtime``, then the project-root ``runtime/``.
    """
    runtime_dir = os.environ.get("BT_RUNTIME_DIR")
    if runtime_dir:
        return resolve_path(runtime_dir)

    # Fallback: Try to find 'runtime' in the project root or up one level
    # Development: cli/../runtime -> ROOT/runtime
    local_runtime = os.path.join(ROOT, 'runtime')
    if os.path.exists(local_runtime):
        return local_runtime

    # Production/Alternative: ROOT/../runtime
    up_runtime = os.path.abspath(os.path.join(ROOT, '..', 'runtime'))
    if os.path.exists(up_runtime):
        return up_runtime

    return ""
