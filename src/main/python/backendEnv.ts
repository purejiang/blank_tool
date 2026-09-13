import { PATH_CONFIG_DEFAULTS } from '../../shared/config/pathConfig';

export interface BackendRuntimeOverrides {
    javaBin?: string
    nodeBin?: string
}

/**
 * Env for the Python backend. `BT_JAVA_BIN` / `BT_NODE_BIN` are injected ONLY
 * when the user configured a path in Settings — an empty override must leave
 * the variable absent so the backend keeps its own discovery chain
 * (java: BT_JAVA_BIN → runtime/jre → JAVA_HOME → PATH).
 *
 * `BT_PYTHON_BIN` is deliberately NOT injected: `pythonExecutable` IS the
 * interpreter we spawn, and `build.info.python_path` reports it back.
 *
 * Kept dependency-free (no electron / store imports) so it can be unit tested.
 */
export function buildBackendEnv(
    base: Record<string, string | undefined>,
    overrides: BackendRuntimeOverrides = {}
): Record<string, string | undefined> {
    const env: Record<string, string | undefined> = { ...base }
    const javaBin = (overrides.javaBin || '').trim()
    const nodeBin = (overrides.nodeBin || '').trim()
    if (javaBin) {
        env.BT_JAVA_BIN = javaBin
    } else {
        delete env.BT_JAVA_BIN
    }
    if (nodeBin) {
        env.BT_NODE_BIN = nodeBin
    } else {
        delete env.BT_NODE_BIN
    }
    return env
}

/** Runtime override keys read from the app config store. */
export const RUNTIME_OVERRIDE_KEYS = {
    java: 'javaPath',
    python: 'pythonPath',
    node: 'nodePath'
} as const;

/** Default value used when the user has not overridden a runtime path. */
export const NODE_PATH_DEFAULT = PATH_CONFIG_DEFAULTS.nodePath;
