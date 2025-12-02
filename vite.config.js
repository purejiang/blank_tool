import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  root: 'src',
  plugins: [vue()],
  base: './',
  build: {
    outDir: 'dist/renderer', // 调整输出目录
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'src/index.html')
      },
      output: {
        format: 'iife'
      }
    }
  },
  server: {
    port: 3000,
    strictPort: true
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src/renderer'), // 调整别名路径
      '@components': resolve(__dirname, 'src/renderer/components'),
      '@views': resolve(__dirname, 'src/renderer/views'),
      '@services': resolve(__dirname, 'src/renderer/services'),
      '@utils': resolve(__dirname, 'src/renderer/utils'),
      '@stores': resolve(__dirname, 'src/renderer/stores'),
      '@assets': resolve(__dirname, 'src/renderer/assets')
    }
  },
  define: {
    global: 'globalThis',
    'process.env': {}
  },
  optimizeDeps: {
    include: ['vue', 'vue-router'],
    exclude: []
  }
})