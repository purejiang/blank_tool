export const PATH_CONFIG_DEFAULTS = {
  // `runtime/` is the container of the bundled tools + the embedded Python
  // interpreter. It ships with the app, so it is deliberately NOT
  // user-configurable (it has no APP_CONFIG_KEYS entry) — this default is the
  // single source of truth.
  runtime: '.\\runtime',
  server: '.\\backend',
  serverEntry: 'main.py',
  runtimeExecutable: 'python\\python.exe',
  // Empty = follow whatever the app itself runs on (Electron's bundled Node).
  nodePath: '',
  devServerUrl: 'http://localhost:3000',
  rendererEntry: 'renderer\\index.html',
  preloadCandidates: [
    'preload\\index.mjs',
    'preload\\preload.mjs',
    'preload\\index.js',
    'preload\\preload.js',
    'preload\\index.cjs',
    'preload\\preload.cjs'
  ]
} as const

export const APP_CONFIG_KEYS = {
  server: 'server',
  serverEntry: 'serverEntry',
  runtimeExecutable: 'runtimeExecutable',
  nodePath: 'nodePath',
  devServerUrl: 'devServerUrl',
  rendererEntry: 'rendererEntry',
  preloadCandidates: 'preloadCandidates'
} as const

export type WritableAppConfigKey =
  | 'app'
  | 'server'
  | 'serverEntry'
  | 'runtimeExecutable'
  | 'devServerUrl'
  | 'rendererEntry'
  | 'preloadCandidates'
  | 'commands'
  | 'logs'
  | 'output'
  | 'language'
  | 'theme'
  | 'timeout'
  | 'enableNotifications'
  | 'autoDeleteOutputOnTaskRemove'
  | 'useProxyForDownload'
  | 'automation'
  | 'adbPath'
  | 'aaptPath'
  | 'apktoolPath'
  | 'bundletoolPath'
  | 'javaPath'
  | 'nodePath'
  | 'signatureConfigs'
