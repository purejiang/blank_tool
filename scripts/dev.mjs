import { spawn } from 'node:child_process';
import { existsSync, statSync } from 'node:fs';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * `npm run dev` 的包装脚本。
 *
 * 为什么不直接 `vite`：vite-plugin-electron 在 **Electron 退出时会连带结束 vite 进程**
 * （`dist/index.mjs`: `process.electronApp.once('exit', process.exit)`），并在退出时用
 * `taskkill` 清理那个已经死掉的 PID（同文件 `treeKillSync`）。于是"Electron 启动即退出"
 * 这种最常见的失败，在终端里只剩一句误导性的：
 *
 *     ERROR: The process "18468" not found.
 *
 * 看起来像 vite 挂了，实际是 Electron 挂了。本脚本不改插件行为，只在退出时把结论说清楚，
 * 并把判断"是 Electron 本身跑不起来还是工程坏了"的方式指向 `npm run doctor`。
 */
const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '..');
const viteBin = resolve(root, 'node_modules', 'vite', 'bin', 'vite.js');
const mainBundle = resolve(root, 'dist', 'main', 'main.js');

function mtimeOf(file) {
  try {
    return statSync(file).mtimeMs;
  } catch {
    return 0;
  }
}

function formatCode(code) {
  const unsigned = code >>> 0;
  if (code < 0 || unsigned >= 0x80000000) {
    return `${code} (0x${unsigned.toString(16).toUpperCase().padStart(8, '0')})`;
  }
  return String(code);
}

function printDiagnosis(exitCode, bundleMtime) {
  const line = '─'.repeat(72);
  console.error(`\n[dev] ${line}`);
  console.error(`[dev] vite 退出码 ${formatCode(exitCode)}，但这次主进程产物是重新构建成功的：`);
  console.error(`[dev]   ${relative(root, mainBundle)}  (${new Date(bundleMtime).toLocaleString()})`);
  console.error('[dev]');
  console.error('[dev] 构建没问题，失败在 Electron 这一侧：要么被拉起后立刻退出，要么卡在自己的');
  console.error('[dev] 启动错误上（见下面第二种形态）。vite-plugin-electron 在 Electron 退出时会');
  console.error('[dev] 连带结束 vite，随后用 taskkill 清理那个已经死掉的 PID，所以末尾那条');
  console.error('[dev] `ERROR: The process "NNNN" not found.` 只是清理噪音，不是失败原因');
  console.error('[dev] （见 node_modules/vite-plugin-electron/dist/index.mjs）。');
  console.error('[dev]');
  console.error('[dev] 判断是「Electron 本身跑不起来」还是「工程坏了」：');
  console.error('[dev]   npm run doctor');
  console.error('[dev] 看崩溃记录（正常情况这里没有 electron.exe 记录）：');
  console.error("[dev]   Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Error'} " +
    "-MaxEvents 30 | Where-Object Message -match 'electron'");
  console.error('[dev] 常见原因：360 主动防御 / 腾讯 iOA 等安全软件拦截 electron.exe、输入法 DLL');
  console.error('[dev] 注入、或系统刚重启前的不稳定状态。详见 docs/04-开发指南.md。');
  console.error('[dev]');
  console.error('[dev] 另一类失败长这样（这时 vite 不会退出，Electron 卡在错误对话框上）：');
  console.error('[dev]   App threw an error during load');
  console.error('[dev]   Error: EPERM: operation not permitted, open ...\\blanks\\app-config.json.tmp-...');
  console.error('[dev] 那是 Electron 进程写不了 %APPDATA%\\blanks（安全软件的文件保护/防勒索在拦');
  console.error('[dev] "写 tmp 再 rename"）—— 把该目录加白名单或临时关掉防勒索；`npm run doctor` 的');
  console.error('[dev] 探针 App 会复现这一项。');
  console.error(`[dev] ${line}\n`);
}

if (!existsSync(viteBin)) {
  console.error(`[dev] 找不到 vite 入口：${viteBin}`);
  console.error('[dev] 先跑 `npm install`（依赖缺失或 node_modules 被破坏）。');
  process.exit(1);
}

const bundleMtimeBefore = mtimeOf(mainBundle);
console.log('[dev] 启动 vite（vite-plugin-electron 会自行拉起 Electron 主进程 / preload）...');

const child = spawn(process.execPath, [viteBin], {
  cwd: root,
  stdio: 'inherit',
  env: process.env,
});

child.on('error', (err) => {
  console.error('[dev] 启动 vite 失败：', err.message);
  process.exit(1);
});

child.on('exit', (code, signal) => {
  const bundleMtimeAfter = mtimeOf(mainBundle);
  const rebuilt = bundleMtimeAfter > bundleMtimeBefore;

  if (typeof code !== 'number') {
    // 没拿到退出码 = 被信号终止（通常是 Ctrl+C），不用解释
    if (signal && signal !== 'SIGINT' && signal !== 'SIGTERM') {
      console.error(`\n[dev] vite 被信号 ${signal} 终止。`);
    }
    process.exit(130);
  }

  if (code !== 0 && rebuilt) {
    printDiagnosis(code, bundleMtimeAfter);
  } else if (code !== 0) {
    console.error(`\n[dev] vite 退出，退出码 ${formatCode(code)}（本次未重建主进程产物，请先看上方 vite 自己的报错）。`);
  }

  process.exit(code);
});
