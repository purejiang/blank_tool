import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: '.',
  timeout: 30000,
  // E2E 推迟到 /workflows 与 /tasks 落地后编写（见 README.md）。当前无 spec
  // 文件，passWithNoTests 保证 `npm run check:full` 里的 Playwright 步骤不会因
  // "no tests found" 而 exit 1；写入真实 spec 后该选项自动失效。
  passWithNoTests: true,
  use: {
    // vite dev server 实际监听 3000（strictPort），不是 5173。
    baseURL: 'http://localhost:3000',
    browserName: 'chromium',
    headless: true,
  },
})
