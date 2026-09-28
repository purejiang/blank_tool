import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      // ⚠️ 这里的 '@' 指向 src，和 vite.config.ts 的 src/renderer **不同**：
      // 测试统一写 `@/renderer/...` 和 `@/shared/...`，靠这一条同时命中两侧；
      // 应用侧源码不写 '@'，只写下面这些具名别名，所以两边不会打架。
      // 具名别名必须与 vite.config.ts 保持一致，少一个就会让被测组件 import 失败。
      '@': path.resolve(__dirname, 'src'),
      '@components': path.resolve(__dirname, 'src/renderer/components'),
      '@views': path.resolve(__dirname, 'src/renderer/views'),
      '@stores': path.resolve(__dirname, 'src/renderer/stores'),
      '@services': path.resolve(__dirname, 'src/renderer/services'),
      '@utils': path.resolve(__dirname, 'src/renderer/utils'),
      '@assets': path.resolve(__dirname, 'src/renderer/assets'),
      '@composables': path.resolve(__dirname, 'src/renderer/composables'),
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    include: ['tests/**/*.test.{ts,mts}'],
    exclude: [
      'tests/e2e/**',
      'tests/shared-contracts.test.mjs',
    ],
    setupFiles: ['tests/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      reportsDirectory: 'tests/reports/coverage',
    },
    reporters: ['default', 'html'],
    outputFile: 'tests/reports/index.html',
  },
})
