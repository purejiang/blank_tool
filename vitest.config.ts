import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      // NOTE: kept as `src` (not `src/renderer`) — existing tests import via
      // `@/renderer/...`; changing it would break them.
      '@': path.resolve(__dirname, 'src'),
    '@components': path.resolve(__dirname, 'src/renderer/components'),
    '@views': path.resolve(__dirname, 'src/renderer/views'),
    '@stores': path.resolve(__dirname, 'src/renderer/stores'),
    '@services': path.resolve(__dirname, 'src/renderer/services'),
    '@utils': path.resolve(__dirname, 'src/renderer/utils'),
    '@composables': path.resolve(__dirname, 'src/renderer/composables'),
    '@assets': path.resolve(__dirname, 'src/renderer/assets'),
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
