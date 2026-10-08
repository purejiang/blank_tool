import { execSync } from 'child_process';
import { mkdirSync, readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

/**
 * ⚠️ 构建期临时目录固定在仓库内（`.tmp-build`），**不要**用系统 %TEMP%。
 *
 * 为什么：Vite 在 `target !== 'esnext'` 或开启压缩时会把**整个 chunk** 交给 esbuild，而 esbuild
 * 的 JS API 对超过 1 MiB 的载荷不走管道，而是先写 `%TEMP%\esbuild-<hex>`，再由 Go 侧读走并删除
 * （`node_modules/esbuild/lib/main.js`：`input.length > 1024 * 1024`）。
 *
 * 2026-10-08 实测：这台机器上**从 F:\ 运行的程序删不掉 `C:\Users\<user>\AppData\Local\Temp`
 * 里的文件**（同一族限制也让 `F:\...\node_modules\electron\dist\electron.exe` 写不了用户目录），
 * 于是 renderer 构建直接挂在：
 *
 *     [vite:esbuild-transpile] remove C:\...\Temp\esbuild-<hex>: Access is denied.
 *
 * 把 TEMP/TMP 指到仓库内（与 esbuild 同盘、可写可删）后构建稳定；`.tmp-build` 已被 `.gitignore`
 * 的 `.tmp*` 规则覆盖，落点可用 `BLANKS_BUILD_TEMP` 覆盖。
 * 注意：这只是绕开机器侧限制，根治仍然是把安全产品对 F:\ 的限制去掉。
 */
const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '..');
const pkgPath = resolve(root, 'package.json');

async function main() {
  const args = process.argv.slice(2);
  // Platform is the first non-flag argument, defaults to 'win'
  const platformIdx = args.findIndex(a => !a.startsWith('--'));
  const platform = platformIdx >= 0 ? args[platformIdx] : 'win';
  const extraArgs = args.filter(a => a !== platform).join(' ');

  const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
  console.log(`[build] Version: ${pkg.version}`);
  console.log(`[build] Platform: ${platform}`);

  // 见文件顶部注释：esbuild 超过 1 MiB 的载荷会经由系统 %TEMP%，这里把它换到仓库内。
  const buildTemp = process.env.BLANKS_BUILD_TEMP || resolve(root, '.tmp-build');
  mkdirSync(buildTemp, { recursive: true });
  process.env.TEMP = buildTemp;
  process.env.TMP = buildTemp;
  console.log(`[build] TEMP/TMP -> ${buildTemp}`);

  // Step 1: Build Vite (main + preload + renderer)
  console.log('[build] Building Vite...');
  execSync('npx vite build', { cwd: root, stdio: 'inherit' });

  // Step 2: Package with electron-builder
  const cmd = `npx electron-builder --${platform}${extraArgs ? ' ' + extraArgs : ''}`;
  console.log(`[build] Running: ${cmd}`);
  execSync(cmd, { cwd: root, stdio: 'inherit' });

  console.log('[build] Done!');
}

main().catch(e => {
  console.error('[build] Error:', e.message);
  process.exit(1);
});
