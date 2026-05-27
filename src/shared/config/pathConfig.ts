export const PATH_CONFIG_DEFAULTS = {
  runtime: '.\\runtime',
  server: '.\\backend',
  serverEntry: 'main.py',
  runtimeExecutable: 'python\\python.exe',
  devServerUrl: 'http://localhost:3000',
  rendererEntry: '..\\renderer\\index.html',
  preloadCandidates: [
    '..\\preload\\index.mjs',
    '..\\preload\\preload.mjs',
    '..\\preload\\index.js',
    '..\\preload\\preload.js',
    '..\\preload\\index.cjs',
    '..\\preload\\preload.cjs'
  ]
} as const

export const APP_CONFIG_KEYS = {
  runtime: 'runtime',
  server: 'server',
  serverEntry: 'serverEntry',
  runtimeExecutable: 'runtimeExecutable',
  devServerUrl: 'devServerUrl',
  rendererEntry: 'rendererEntry',
  preloadCandidates: 'preloadCandidates'
} as const

export type WritableAppConfigKey =
  | 'app'
  | 'runtime'
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
  | 'autoSave'
  | 'enableNotifications'
  | 'adbPath'
  | 'aaptPath'
  | 'apktoolPath'
  | 'bundletoolPath'
  | 'javaPath'
