import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    '@stores': path.resolve(__dirname, 'src/renderer/stores'),
    '@services': path.resolve(__dirname, 'src/renderer/services'),
    '@utils': path.resolve(__dirname, 'src/renderer/utils'),
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
