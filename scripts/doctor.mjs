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
 *      又在 Electron 进程内对三个位置各做一次 `写 tmp + rename`（模拟 electron-store 的
 *      原子写）：userData、`%TEMP%`、仓库内的工作区目录。后者能复现真实应用加载期抛的
 *      `EPERM ... app-config.json.tmp-...`，并区分三档：
 *
 *        ok              三个位置都写得进去 —— Electron 侧没问题。
 *        c-drive-denied  C: 用户区域（userData / %TEMP%）被拒，但**工作区可写** ——
 *                        `src/main/dataRoot.ts` 的 dev 回退会接手，dev 仍能起来。
 *        temp-only       只有 %TEMP% 可写 —— 回退会落到临时目录。
 *        all-denied      三个都写不进去 —— 当前环境跑不了 Electron，只能机器侧处理。
 *
 * ⚠️ 必须在**不受 DSH 沙箱限制**的进程里跑（用户自己的终端 / 本机 PowerShell）。
 * 在 workspace-write 沙箱里跑，Electron 拿到的写权限是沙箱给的，结论只反映沙箱，没有意义。
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
/** 第三个探测目标：仓库内的工作区目录 —— dev 回退候选里本机唯一写得进去的位置。
 *  探针只在这里建/删自己的临时子目录，绝不碰 userData / %TEMP% 的既有内容。 */
const DEV_DATA_ROOT = join(root, '.dev-data');
const PROBE_WORKSPACE = join(DEV_DATA_ROOT, 'doctor-probe');

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
      "import { existsSync, mkdirSync, renameSync, rmSync, writeFileSync } from 'node:fs'",
      "import { join } from 'node:path'",
      "import { tmpdir } from 'node:os'",
      '',
      'const workspace = process.env.BLANKS_DOCTOR_WORKSPACE || ""',
      'const targets = [',
      '  ["userData", app.getPath("userData")],',
      '  ["temp", tmpdir()],',
      '  ...(workspace ? [["workspace", workspace]] : []),',
      ']',
      'let userDataBlocked = false',
      'for (const [label, dir] of targets) {',
      '  const target = join(dir, "doctor-probe.json")',
      '  const tmp = target + ".tmp-" + process.pid',
      '  const existed = existsSync(dir)',
      '  try {',
      '    if (!existed) mkdirSync(dir, { recursive: true })',
      '    writeFileSync(tmp, JSON.stringify({ ok: true }))',
      '    renameSync(tmp, target)',
      '    rmSync(target, { force: true })',
      '    console.log("BLANKS_PROBE_WRITE_OK " + label + " " + dir)',
      '  } catch (err) {',
      '    if (label === "userData") userDataBlocked = true',
      '    console.error("BLANKS_PROBE_WRITE_FAIL " + label + " " + (err && err.code) + " " + dir)',
      '  } finally {',
      '    // 只清理由探针**新建**的那一个目录（工作区项）；userData / %TEMP% 可能是 Electron',
      '    // 自己建的 profile 目录，删掉会连累真实运行。',
      '    if (label === "workspace" && !existed) {',
      '      try { rmSync(dir, { recursive: true, force: true }) } catch {}',
      '    }',
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

/** @returns {'ok'|'c-drive-denied'|'temp-only'|'all-denied'|'failed'} */
function checkProbeApp(electronBinary) {
  console.log('[doctor] B. 最小探针 App（会闪出一个 420x240 的窗口，4 秒后自动关闭）...');
  writeProbeApp();
  console.log(`[doctor]    探针目录：${PROBE_DIR}`);
  console.log(`[doctor]    工作区探测目标：${PROBE_WORKSPACE}`);
  const result = spawnSync(electronBinary, [PROBE_DIR, '--no-sandbox'], {
    encoding: 'utf8',
    timeout: 25000,
    cwd: PROBE_DIR,
    env: { ...process.env, ELECTRON_ENABLE_LOGGING: '1', BLANKS_DOCTOR_WORKSPACE: PROBE_WORKSPACE },
  });
  outputOf(result).forEach((l) => console.log(`[doctor]    ${l}`));
  const noise = `${result.stdout || ''}\n${result.stderr || ''}`;
  const timedOut = result.error && result.error.code === 'ETIMEDOUT';

  let verdict = 'failed';
  const userDataFailed = /BLANKS_PROBE_WRITE_FAIL userData/.test(noise);
  const tempOk = /BLANKS_PROBE_WRITE_OK temp/.test(noise);
  const workspaceOk = /BLANKS_PROBE_WRITE_OK workspace/.test(noise);
  if (userDataFailed) {
    // C: 用户区域被拒时工作区还写得进去吗？这一档决定 dev 回退能不能救回来。
    if (workspaceOk) {
      verdict = 'c-drive-denied';
    } else if (tempOk) {
      verdict = 'temp-only';
    } else {
      verdict = 'all-denied';
    }
  } else if (result.status === 0 && !timedOut) {
    verdict = 'ok';
  }

  const verdictLine =
    verdict === 'ok'
      ? PASS
      : verdict === 'c-drive-denied'
        ? `${FAIL}（C: 用户区域被拒；工作区可写 → dev 会自动回退）`
        : verdict === 'temp-only'
          ? `${FAIL}（C: 用户区域被拒；只有 %TEMP% 可写）`
          : verdict === 'all-denied'
            ? `${FAIL}（三个位置全被拒）`
            : FAIL;
  console.log(`[doctor]    exit code = ${formatCode(result.status)}${timedOut ? '（超时未退出）' : ''} -> ${verdictLine}`);
  if (/crashpad/i.test(noise)) {
    console.log('[doctor]    注意：日志里出现 crashpad（崩溃处理器连不上），常见于安全软件拦截 / 进程被提前打死。');
  }
  if (verdict === 'c-drive-denied') {
    console.log('[doctor]    Electron 能启动，但**写不了 C: 用户区域**（userData 与 %TEMP% 都 EPERM），');
    console.log('[doctor]    而仓库所在的工作区目录可写 —— 限制是按 electron.exe 这个镜像做的位置限制。');
    console.log('[doctor]    真实应用会在加载期抛 `EPERM ... app-config.json.tmp-...`，这就是那个弹窗的来源；');
    console.log('[doctor]    `npm run dev` 会自动把数据目录回退到 <仓库>\\.dev-data（src/main/dataRoot.ts），所以 dev 仍能起来。');
  }
  if (verdict === 'all-denied') {
    console.log('[doctor]    连工作区都写不进去 —— 这个进程在当前环境下无法运行 Electron（不是仓库代码的问题）。');
  }
  if (verdict === 'temp-only') {
    console.log('[doctor]    工作区被拒但 %TEMP% 可写 —— dev 回退会落到临时目录（数据不持久，仅够起 App）。');
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
    console.log('[doctor] （注意：这台机器上它是**间歇性**的，过几分钟可能又能起；但能起也只是进到下面「写不了 C: 用户区域」那一档。）');
  } else if (probeVerdict === 'c-drive-denied') {
    console.log('[doctor] 结论：Electron 能启动、能开窗，但**写不了 C: 用户区域**（userData / %TEMP% 都 EPERM），');
    console.log('[doctor] 而工作区目录可写 —— `App threw an error during load ... EPERM ... app-config.json.tmp-...`');
    console.log('[doctor] 就是这么来的：electron-store 在模块加载期就要写 app-config.json，写不进去 App 直接起不来。');
    console.log('[doctor] 2026-10-08 实测：node.exe 对同样这些路径全部可写，而 `ELECTRON_RUN_AS_NODE=1` 的 electron.exe');
    console.log('[doctor] 和完整 Electron 主进程表现一致 —— 限制挂在 electron.exe 这个镜像上，且按位置划分（C: 用户区域）。');
    console.log('[doctor] 所以**改目录名没用**（连 %APPDATA% 根目录都被拒），换位置有用：');
    console.log('[doctor] `npm run dev` 会自动把数据目录回退到 <仓库>\\.dev-data（src/main/dataRoot.ts），dev 仍能起来。');
  } else if (probeVerdict === 'temp-only') {
    console.log('[doctor] 结论：Electron 能启动，但 userData 与工作区都写不进去，只有 %TEMP% 可写。');
    console.log('[doctor] dev 回退会落到系统临时目录下的 blanks-dev-data（数据不持久，够起 App 而已）。');
  } else if (probeVerdict === 'all-denied') {
    console.log('[doctor] 结论：三个探测位置（userData / %TEMP% / 工作区）**全都写不进去** ——');
    console.log('[doctor] 当前环境下 Electron 进程无法写任何文件，App 起不来，仓库代码改不动这件事。');
  } else {
    console.log('[doctor] 结论：`--version` 能过但探针 App 失败 —— 重点看开窗/GPU 路径。');
  }

  if (!healthy) {
    console.log('[doctor] 排查顺序（从便宜到麻烦）：');
    if (probeVerdict === 'c-drive-denied' || probeVerdict === 'temp-only' || probeVerdict === 'all-denied') {
      console.log('[doctor]   要放行的是**electron.exe 这个可执行文件本身**，不是某个数据目录 —— 换目录名没用，已实测：');
      console.log('[doctor]   1. 先确认是谁在拦：本机 2026-10-08 没查到 360 / 腾讯管家 / iOA 的进程或驱动，Defender 的');
      console.log('[doctor]      「受控文件夹访问」与 Smart App Control 也都是关的 —— 按"谁装了文件过滤驱动"去找。');
      console.log('[doctor]   2. 360 安全卫士：信任区加文件 node_modules/electron/dist/electron.exe 与项目根，');
      console.log('[doctor]      并检查「主动防御 / 沙箱（360Box）」是否把 electron.exe 收进了只读容器；必要时先临时退出 360 验证。');
      console.log('[doctor]   3. 腾讯 iOA / 无边界安全系统防护：请 IT 把 electron.exe 加白名单，或查它的拦截记录');
      console.log('[doctor]      （文档保护模块会在 C:/ProgramData/Tencent/QQPCMgr/Tfsdocpro/ 下留带时间戳的扫描记录）。');
      console.log('[doctor]   4. 重启机器（内核 hook / 安全软件状态卡死时最有效）；输入法切到微软拼音。');
      console.log('[doctor]   5. 每改一项就跑一次 npm run doctor + npm run dev（一次只动一个，才能定位到是哪个产品）。');
      console.log('[doctor]   不阻塞开发：c-drive-denied 会回退到工作区、temp-only 会回退到临时目录；只有 all-denied 才真起不来。');
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
  console.log(`[doctor] dev 回退目录 ${DEV_DATA_ROOT} -> ${existsSync(DEV_DATA_ROOT) ? '已创建' : '还没创建（默认目录可写时不会创建）'}`);

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
