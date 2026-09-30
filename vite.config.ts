import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import electron from 'vite-plugin-electron/simple'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

/**
 * 主进程 / 预载脚本的公共构建选项。
 *
 * ⚠️ 这两行不是"顺手调优"，是绕开一个会**直接中断构建**的坑：
 *
 * Vite 只在 `target !== 'esnext'` 或 `minify === 'esbuild'` 时，才会把**整块 chunk**
 * 交给 esbuild 再 transform 一次（见 node_modules/vite/dist/node/chunks/dep-*.js 的
 * `resolveEsbuildTranspileOptions`）。主进程 bundle 有 1.4 MB，而 esbuild 的 JS API 对
 * 超过 1 MiB 的载荷不走管道、而是**先写临时文件** `%TEMP%\esbuild-<hex>`
 * （node_modules/esbuild/lib/main.js: `input.length > 1024 * 1024`），再由 esbuild 的
 * Go 侧读走并删除。那次删除在某些 Windows 环境（杀软实时扫描 / 安全删除垫片）会被拒，
 * esbuild 就把它当成构建错误抛出来：
 *
 *     [vite:esbuild-transpile] remove C:\...\Temp\esbuild-<hex>: Access is denied.
 *
 * 于是 `npm run dev` 里主进程构建直接失败（Electron 起不来），dist/main/main.js 停在旧版本。
 * 把 target 定成 esnext 且关掉 esbuild 压缩后，Vite 会跳过这次整块 transform（载荷不再
 * 经过临时文件），dev 与打包都稳。
 *
 * 代价：主进程/预载产物不压缩（main.js ~1.3 MB 而不是 ~860 KB）。Electron 主进程跑在
 * 固定的 Node/Chromium 上、也不需要降级语法，这点体积换"构建确定性"划算。
 * 如果哪天想要回压缩：把 minify 改回 `'esbuild'` —— 上面那个临时文件的坑会一起回来。
 */
const electronBuild = {
  target: 'esnext',
  minify: false,
}

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
            ...electronBuild,
          },
        },
      },
      preload: {
        input: resolve(__dirname, 'src/preload/index.ts'),
        vite: {
          build: {
            outDir: resolve(__dirname, 'dist/preload'),
            ...electronBuild,
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
