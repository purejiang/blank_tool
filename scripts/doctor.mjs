import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import os from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * `npm run doctor` —— 判断「Electron 本身能不能在这台机器上跑起来」。
 *
 * 背景：`npm run dev` 最常见的失败形态是 Electron 被拉起后立刻退出，终端里只剩
 * vite-plugin-electron 清理阶段的 `ERROR: The process "NNNN" not found.`，
 * 完全看不出是工程的问题还是机器的/安全软件的问题（详见 docs/04-开发指南.md）。
 *
 * 本脚本做两件事，都不依赖仓库的业务代码：
 *   A. `electron --version`：只打印版本、不加载任何 App。它都跑不通 = Electron 层的问题。
 *   B. 现场生成一个最小 Electron App（临时目录）跑一遍：既能开窗（验证进程/GPU 正常），
 *      又在 Electron 进程内对自己的 userData 做一次 `写 tmp + rename`（模拟 electron-store
 *      的原子写）。后者能复现真实应用加载期抛的
 *      `EPERM ... app-config.json.tmp-...`（安全软件拦写文件）。
 *
 * 退出码：0 = 全部通过；1 = 任一失败（可直接当门禁用）。
 */
const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '..');
const requireFromRoot = createRequire(join(root, 'package.json'));

/** 探针 App 的包名刻意用 `blanks`：userData 才会落在真实应用同一个目录（%APPDATA%\blanks），
 *  这样"写不进去"这类按目录/按进程放行的拦截规则才能被如实复现。探针只写自己的
 *  doctor-probe.json 并立即删除，不碰 app-config.json。 */
const PROBE_APP_NAME = 'blanks';
const PROBE_DIR = join(os.tmpdir(), 'blanks-electron-probe');

const PASS = 'PASS';
const FAIL = 'FAIL';

function pkgVersion(name) {
  try {
    return JSON.parse(readFileSync(join(root, 'node_modules', name, 'package.json'), 'utf8')).version;
  } catch {
    return '(未安装)';
  }
}

function resolveElectronBinary() {
  // 覆盖钩子：调试 doctor 自身、或 electron 不在 node_modules 时用（指到一个可执行的
  // electron 兼容程序即可，doctor 只依赖它的 argv 约定与退出码）。
  const override = (process.env.BLANKS_DOCTOR_ELECTRON || '').trim();
  if (override) {
    if (existsSync(override)) return override;
    console.error(`[doctor] BLANKS_DOCTOR_ELECTRON 指向的文件不存在：${override}`);
    process.exit(1);
  }
  try {
    const fromPkg = requireFromRoot('electron');
    if (typeof fromPkg === 'string' && existsSync(fromPkg)) return fromPkg;
  } catch {
    /* fall through */
  }
  const fallback = join(root, 'node_modules', 'electron', 'dist', 'electron.exe');
  return existsSync(fallback) ? fallback : null;
}

function formatCode(code) {
  if (typeof code !== 'number') return String(code);
  const unsigned = code >>> 0;
  if (code < 0 || unsigned >= 0x80000000) {
    const hex = unsigned.toString(16).toUpperCase().padStart(8, '0');
    return `${code} (0x${hex})`;
  }
  return String(code);
}

function outputOf(result) {
  const parts = [];
  parts.push(`stdout: ${String(result.stdout || '').trim() || '(空)'}`);
  if (result.stderr) parts.push(`stderr: ${String(result.stderr).trim()}`);
  if (result.error) parts.push(`error: ${result.error.message}`);
  return parts;
}

function checkVersion(electronBinary) {
  console.log('[doctor] A. electron --version（不加载任何 App；失败时重试，因为这台机器上它是间歇性的）...');
  let ok = false;
  for (let attempt = 1; attempt <= 3; attempt++) {
    const result = spawnSync(electronBinary, ['--version', '--no-sandbox'], {
      encoding: 'utf8',
      timeout: 20000,
      windowsHide: true,
      cwd: root,
    });
    const stdout = String(result.stdout || '').trim();
    ok = result.status === 0 && /v?\d+\.\d+\.\d+/.test(stdout);
    console.log(`[doctor]    第 ${attempt} 次：exit code = ${formatCode(result.status)} stdout=${stdout || '(空)'} -> ${
      ok ? PASS : FAIL
    }`);
    if (ok) break;
    if (attempt < 3) sleepSync(4000);
  }
  if (!ok) {
    console.log('[doctor]    三次都没起来：这次探测期间 electron.exe 启动即被中断（0x80000003 = 快速失败）。');
  }
  return ok;
}

/** 同步 sleep：doctor 是纯 CLI 脚本，不引第三方依赖。 */
function sleepSync(ms) {
  const shared = new SharedArrayBuffer(4);
  Atomics.wait(new Int32Array(shared), 0, 0, ms);
}

function writeProbeApp() {
  mkdirSync(PROBE_DIR, { recursive: true });
  writeFileSync(
    join(PROBE_DIR, 'package.json'),
    JSON.stringify(
      { name: PROBE_APP_NAME, version: '1.0.0', private: true, type: 'module', main: 'main.js' },
      null,
      2,
    ) + '\n',
    'utf8',
  );
  writeFileSync(
    join(PROBE_DIR, 'main.js'),
    [
      "import { app, BrowserWindow } from 'electron'",
      "import { renameSync, rmSync, writeFileSync } from 'node:fs'",
      "import { join } from 'node:path'",
      "import { tmpdir } from 'node:os'",
      '',
      'const targets = [',
      '  ["userData", app.getPath("userData")],',
      '  ["temp", tmpdir()],',
      ']',
      'let userDataBlocked = false',
      'for (const [label, dir] of targets) {',
      '  const target = join(dir, "doctor-probe.json")',
      '  const tmp = target + ".tmp-" + process.pid',
      '  try {',
      '    writeFileSync(tmp, JSON.stringify({ ok: true }))',
      '    renameSync(tmp, target)',
      '    rmSync(target, { force: true })',
      '    console.log("BLANKS_PROBE_WRITE_OK " + label + " " + dir)',
      '  } catch (err) {',
      '    if (label === "userData") userDataBlocked = true',
      '    console.error("BLANKS_PROBE_WRITE_FAIL " + label + " " + (err && err.code) + " " + dir)',
      '  }',
      '}',
      'if (userDataBlocked) app.exit(3)',
      '',
      'const win = new BrowserWindow({ width: 420, height: 240, show: true })',
      "win.loadURL('data:text/html,<h1>Electron OK</h1>')",
      'setTimeout(() => app.quit(), 4000)',
      '',
    ].join('\n'),
    'utf8',
  );
}

/** @returns {'ok'|'write-denied'|'failed'} */
function checkProbeApp(electronBinary) {
  console.log('[doctor] B. 最小探针 App（会闪出一个 420x240 的窗口，4 秒后自动关闭）...');
  writeProbeApp();
  console.log(`[doctor]    探针目录：${PROBE_DIR}`);
  const result = spawnSync(electronBinary, [PROBE_DIR, '--no-sandbox'], {
    encoding: 'utf8',
    timeout: 25000,
    cwd: PROBE_DIR,
    env: { ...process.env, ELECTRON_ENABLE_LOGGING: '1' },
  });
  outputOf(result).forEach((l) => console.log(`[doctor]    ${l}`));
  const noise = `${result.stdout || ''}\n${result.stderr || ''}`;
  const timedOut = result.error && result.error.code === 'ETIMEDOUT';

  let verdict = 'failed';
  const userDataFailed = /BLANKS_PROBE_WRITE_FAIL userData/.test(noise);
  const tempFailed = /BLANKS_PROBE_WRITE_FAIL temp/.test(noise);
  if (userDataFailed) {
    verdict = 'write-denied';
  } else if (result.status === 0 && !timedOut) {
    verdict = 'ok';
  }

  console.log(`[doctor]    exit code = ${formatCode(result.status)}${timedOut ? '（超时未退出）' : ''} -> ${
    verdict === 'ok' ? PASS : FAIL
  }`);
  if (/crashpad/i.test(noise)) {
    console.log('[doctor]    注意：日志里出现 crashpad（崩溃处理器连不上），常见于安全软件拦截 / 进程被提前打死。');
  }
  if (verdict === 'write-denied') {
    console.log('[doctor]    Electron 能启动，但**在 Electron 进程内写不了自己的 userData 目录**：');
    console.log('[doctor]    真实应用会在加载期直接抛 `EPERM ... app-config.json.tmp-...` 并停在错误对话框上。');
    if (tempFailed) {
      console.log('[doctor]    连 %TEMP% 也写不了 —— 这不是某个目录的 ACL，而是**整个 Electron 进程被按只读/沙箱方式运行**。');
      console.log('[doctor]    已实测：读文件正常、node.exe 写同一路径正常、连 `ELECTRON_RUN_AS_NODE=1` 的 electron.exe 都写不了。');
    }
  }

  if (verdict === 'ok') {
    try {
      rmSync(PROBE_DIR, { recursive: true, force: true });
      console.log('[doctor]    探针目录已清理。');
    } catch {
      console.log('[doctor]    探针目录清理失败，可手动删除。');
    }
  } else {
    console.log('[doctor]    探针目录保留，便于取证。');
  }
  return verdict;
}

function printReport({ versionOk, probeVerdict, electronBinary }) {
  const line = '─'.repeat(72);
  console.log(`[doctor] ${line}`);

  const healthy = versionOk && probeVerdict === 'ok';
  if (healthy) {
    console.log('[doctor] 结论：Electron 正常 —— 若 npm run dev 仍失败，请看 vite 自己的报错（工程侧问题）。');
  } else if (!versionOk) {
    console.log('[doctor] 结论：三次 `electron --version` 都没起来 —— 这次探测期间 electron.exe 被系统层打断了。');
    console.log('[doctor] （注意：这台机器上它是**间歇性**的，过几分钟可能又能起；但能起也只是进到下面「只读」那一档。）');
  } else if (probeVerdict === 'write-denied') {
    console.log('[doctor] 结论：Electron 能启动，但进程内写不了自己的用户数据目录 —— 这就是');
    console.log('[doctor] `App threw an error during load ... EPERM ... app-config.json.tmp-...` 的来源。');
    console.log('[doctor] electron-store 在模块加载期就要写 app-config.json，写不进去 App 直接起不来。');
    console.log('[doctor] 这台机器上实测的形态是：Electron 进程内**读得到、写不了**（连 %TEMP% 也 EPERM），');
    console.log('[doctor] 而 node.exe / PowerShell 写同一路径正常 —— 限制挂在 electron.exe 这个镜像上，');
    console.log('[doctor] 是安全产品在按"只读容器/沙箱"运行它，与本仓库代码无关。');
  } else {
    console.log('[doctor] 结论：`--version` 能过但探针 App 失败 —— 重点看开窗/GPU 路径。');
  }

  if (!healthy) {
    console.log('[doctor] 排查顺序（从便宜到麻烦）：');
    if (probeVerdict === 'write-denied') {
      console.log('[doctor]   限制挂在 electron.exe 这个镜像上，所以要放行的是**这个可执行文件本身**，不是某个目录：');
      console.log('[doctor]   1. 360 安全卫士：信任区加文件 node_modules\\electron\\dist\\electron.exe（以及项目根目录），');
      console.log('[doctor]      并检查「主动防御 / 沙箱（360Box）」是否把 electron.exe 当未知程序收进了只读容器；必要时先临时退出 360 验证。');
      console.log('[doctor]   2. 腾讯 iOA / 无边界安全系统防护：请 IT 把 electron.exe 加白名单，或在其控制台查该进程的拦截记录。');
      console.log('[doctor]      它的「文档保护」模块在写 C:\\ProgramData\\Tencent\\QQPCMgr\\Tfsdocpro\\*（时间戳可用来对账）。');
      console.log('[doctor]   3. 每改一项就跑一次 npm run doctor + npm run dev（一次只动一个，才能定位到是哪个产品）。');
      console.log('[doctor]   4. 不要用「node / PowerShell 能写同一路径」来否定它 —— 限制只作用在 electron.exe 上，已实测。');
    } else {
      console.log('[doctor]   1. 重启机器（内核 hook / 安全软件状态卡死时最有效）。');
      console.log('[doctor]   2. 360 主动防御：临时关闭，或把项目根 + node_modules\\electron\\dist + %APPDATA%\\blanks 加入信任区。');
      console.log('[doctor]   3. 腾讯 iOA（无边界安全系统防护 / txinj 注入驱动）：请 IT 放行 electron.exe 或查拦截日志。');
      console.log('[doctor]   4. 输入法：切到微软拼音 / 退出微信输入法（wetype_tip_core.dll 会注入主进程）。');
      console.log('[doctor]   5. Get-ChildItem -Recurse .\\node_modules\\electron | Unblock-File（清文件标记）。');
    }
    console.log('[doctor]   末位手段：以上都无效时，这台机器当前无法稳定运行 Electron，只能靠 IT 放行或换机开发。');
    console.log('[doctor] 崩溃/拦截记录：');
    console.log("[doctor]   Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Error'} " +
      "-MaxEvents 30 | Where-Object Message -match 'electron'");
    console.log("[doctor]   Get-WinEvent -LogName 'Microsoft-Windows-CodeIntegrity/Operational' -MaxEvents 100 " +
      "| Where-Object Message -match 'electron'");
  }
  console.log(`[doctor] electron 可执行文件：${electronBinary}`);
  console.log(`[doctor] ${line}`);
  return healthy;
}

function main() {
  console.log('[doctor] Blanks 开发环境自检');
  console.log(`[doctor] node ${process.version} / ${process.platform} ${process.arch}`);
  console.log(`[doctor] 仓库根：${root}`);
  console.log(`[doctor] electron ${pkgVersion('electron')} / vite ${pkgVersion('vite')} / vite-plugin-electron ${pkgVersion('vite-plugin-electron')}`);

  const mainBundle = join(root, 'dist', 'main', 'main.js');
  if (existsSync(mainBundle)) {
    console.log(`[doctor] 主进程产物：${relative(root, mainBundle)} (${statSync(mainBundle).mtime.toLocaleString()})`);
  } else {
    console.log('[doctor] 主进程产物：不存在（还没跑过 `npm run dev` / `npm run build`）');
  }
  const userData = process.env.APPDATA ? join(process.env.APPDATA, 'blanks') : null;
  const localData = process.env.LOCALAPPDATA ? join(process.env.LOCALAPPDATA, 'blanks') : null;
  if (userData) console.log(`[doctor] userData ${userData} -> ${existsSync(userData) ? '已创建' : '还没创建'}`);
  if (localData) console.log(`[doctor] 数据目录 ${localData} -> ${existsSync(localData) ? '已创建' : '还没创建'}`);

  const electronBinary = resolveElectronBinary();
  if (!electronBinary) {
    console.error('[doctor] 找不到 electron 可执行文件：先跑 `npm install`。');
    process.exit(1);
  }

  const versionOk = checkVersion(electronBinary);
  let probeVerdict = 'failed';
  if (!versionOk) {
    console.log('[doctor] B. --version 已失败，跳过探针 App（同一根因，省 25 秒）。');
  } else {
    probeVerdict = checkProbeApp(electronBinary);
  }

  const healthy = printReport({ versionOk, probeVerdict, electronBinary });
  process.exit(healthy ? 0 : 1);
}

main();
