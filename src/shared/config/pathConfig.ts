export const PATH_CONFIG_DEFAULTS = {
  runtime: '.\\runtime',
  // Python 后端根目录：backend/ → cli/ 重命名后同步（打包时 extraResources 只拷 cli/）
  server: '.\\cli',
  serverEntry: 'main.py',
  runtimeExecutable: 'python\\python.exe',
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
  runtime: 'runtime',
  server: 'server',
  serverEntry: 'serverEntry',
  runtimeExecutable: 'runtimeExecutable',
  devServerUrl: 'devServerUrl',
  rendererEntry: 'rendererEntry',
  preloadCandidates: 'preloadCandidates'
} as const

export const WRITABLE_CONFIG_KEYS = {
  app: 'app',
  runtime: 'runtime',
  server: 'server',
  serverEntry: 'serverEntry',
  runtimeExecutable: 'runtimeExecutable',
  devServerUrl: 'devServerUrl',
  rendererEntry: 'rendererEntry',
  preloadCandidates: 'preloadCandidates',
  commands: 'commands',
  logs: 'logs',
  output: 'output',
  language: 'language',
  theme: 'theme',
  enableNotifications: 'enableNotifications',
  autoDeleteOutputOnTaskRemove: 'autoDeleteOutputOnTaskRemove',
  javaPath: 'javaPath'
} as const

export type WritableAppConfigKey = keyof typeof WRITABLE_CONFIG_KEYS
