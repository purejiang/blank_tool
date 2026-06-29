import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import electron from 'vite-plugin-electron/simple'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

export default defineConfig({
  plugins: [
    vue(),
    electron({
      main: {
        entry: resolve(__dirname, 'src/main/main.ts'),
        vite: {
          publicDir: resolve(__dirname, 'src/main/public'),
          build: {
            outDir: resolve(__dirname, 'dist/main'),
          },
        },
      },
      preload: {
        input: resolve(__dirname, 'src/preload/index.ts'),
        vite: {
          build: {
            outDir: resolve(__dirname, 'dist/preload'),
            rollupOptions: {
              output: {
                format: 'es',
                entryFileNames: 'index.mjs'
              }
            }
          },
        },
      },
      renderer: {},
    }),
  ],
  root: 'src',
  publicDir: 'renderer/public',
  base: './',
  build: {
    outDir: '../dist/renderer',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'src/index.html')
      }
    }
  },
  server: {
    port: 3000,
    strictPort: true
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src/renderer'),
      '@components': resolve(__dirname, 'src/renderer/components'),
      '@views': resolve(__dirname, 'src/renderer/views'),
      '@services': resolve(__dirname, 'src/renderer/services'),
      '@utils': resolve(__dirname, 'src/renderer/utils'),
      '@stores': resolve(__dirname, 'src/renderer/stores'),
      '@assets': resolve(__dirname, 'src/renderer/assets'),
      '@composables': resolve(__dirname, 'src/renderer/composables')
    }
  }
})
