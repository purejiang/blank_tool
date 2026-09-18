import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { cpSync, existsSync } from 'fs'
import { defineConfig } from 'electron-vite'
import vue from '@vitejs/plugin-vue'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const MAIN_OUT_DIR = 'dist/main'

// electron-vite 对 main/preload 强制 build.copyPublicDir = false，
// 这里用内联插件复刻原 vite-plugin-electron 的 publicDir 拷贝行为
// （图标随构建进入 dist/main/，mainWindow/tray 按 __dirname/assets/... 取用）
function copyMainPublicAssets(): import('vite').Plugin {
  return {
    name: 'copy-main-public-assets',
    writeBundle() {
      const from = resolve(__dirname, 'src/main/public')
      if (existsSync(from)) {
        cpSync(from, resolve(__dirname, MAIN_OUT_DIR), { recursive: true })
      }
    }
  }
}

export default defineConfig({
  main: {
    plugins: [copyMainPublicAssets()],
    build: {
      outDir: MAIN_OUT_DIR,
      rollupOptions: {
        input: { main: resolve(__dirname, 'src/main/main.ts') }
      }
    }
  },
  preload: {
    build: {
      outDir: 'dist/preload',
      rollupOptions: {
        input: { index: resolve(__dirname, 'src/preload/index.ts') }
      }
    }
  },
  renderer: {
    // index.html 位于 src/（而非约定的 src/renderer/），root 沿用 src
    root: 'src',
    publicDir: 'renderer/public',
    base: './',
    plugins: [vue()],
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
    },
    server: {
      port: 3000,
      strictPort: true
    },
    build: {
      // 注意：electron-vite 的 build.outDir 按**项目根**解析（不是 renderer root），
      // 所以这里必须是 'dist/renderer'。写成 '../dist/renderer'（旧 vite.config.ts
      // 的写法，那里 outDir 相对 root=src）会把产物写到项目**上一级**目录，
      // 导致 electron-builder 打包时 dist/renderer 缺失。
      outDir: 'dist/renderer',
      emptyOutDir: true,
      rollupOptions: {
        input: { main: resolve(__dirname, 'src/index.html') }
      }
    }
  }
})
