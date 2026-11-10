// ============================================================
// scripts/release.mjs — 一键发版全流程
//
// Usage:
//   node scripts/release.mjs                  # default patch bump
//   node scripts/release.mjs --minor          # minor bump
//   node scripts/release.mjs --major          # major bump
//   node scripts/release.mjs --version=2.5.0  # 指定版本号；该 tag 已存在时自动断点续跑
//   node scripts/release.mjs --service-version=2.5.1  # 同时发布服务端版本（后端有改动时用）
//   node scripts/release.mjs --yes            # 跳过交互确认（CI/自动化用）
//   node scripts/release.mjs --dry-run        # preview only
// ============================================================

import { execSync } from 'child_process';
import { readFileSync, writeFileSync, existsSync, unlinkSync, readdirSync } from 'fs';
import { resolve, dirname, join, relative } from 'path';
import { fileURLToPath } from 'url';
import { createInterface } from 'readline';
import { compareVersions } from './lib/version.mjs';

// ============================================================
// Constants
// ============================================================

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '..');
const pkgPath = resolve(root, 'package.json');
const pkgBakPath = resolve(root, 'package.json.bak');
const buildDir = resolve(root, 'build');
// 版本号的其他载体（状态栏「服务端版本」读的是 backend/.env 的 APP_VERSION）
const backendEnvPath = resolve(root, 'backend/.env');
const backendServerConfigExamplePath = resolve(root, 'backend/server.config.example.json');
const MAX_OUTPUT_LENGTH = 50000;

const TIMEOUTS = {
  default: 60000,
  // 质量门禁包含 pytest 契约测试（比 vitest 慢，Windows 上尤甚），5 分钟不够。
  qualityGate: 1200000,
  build: 900000,
  upload: 600000,
};

const HINTS = {
  preflight:
    '检查分支/工作区/认证状态：确保在 dev 分支、工作区干净、gh 已认证、dev 已推送远程',
  quality_gate:
    '修复 lint/typecheck/单测/契约测试失败项，完成后重新运行 npm run release',
  compute_version:
    '检查 tag 是否已存在：可续跑时用 --version=<同版本>；否则用 --version= 指定更大的版本号',
  merge_and_tag:
    '检查网络连接，或手动 git push。merge 冲突解决后：tag 未创建时用 --version=<package.json 当前版本> 重跑，tag 已创建时用 --version=<同版本> 续跑',
  build:
    '检查 vite/electron-builder 构建错误。若只是环境问题（依赖/磁盘/杀软），修复后用 --version=<当前 tag 版本> 重跑即可断点续跑；若改过源码，请换新版本号',
  release:
    '检查 GitHub 权限和网络连接；用 --version=<当前 tag 版本> 重跑会清掉同版本 draft 并从发布阶段继续',
  upload:
    '检查网络连接；用 --version=<当前 tag 版本> 重跑会断点续跑（draft 自动清理重建）',
  cleanup:
    '旧资产清理失败不影响发布，可手动处理',
};

// ============================================================
// Error Infrastructure (TODO 1)
// ============================================================

class ReleaseError extends Error {
  /**
   * @param {string} phase - Phase name (preflight, quality_gate, etc.)
   * @param {string} message - Human-readable error summary
   * @param {object} opts
   * @param {string} [opts.command] - The command that failed
   * @param {number} [opts.exitCode] - Process exit code
   * @param {string} [opts.stdout] - Captured stdout (truncated)
   * @param {string} [opts.stderr] - Captured stderr (truncated)
   * @param {number} [opts.durationMs] - Command duration in ms
   * @param {string} [opts.hint] - Fix suggestion for this phase
   * @param {string} [opts.nextAction] - Recommended next step
   * @param {boolean} [opts.recoverable] - Can the release be retried?
   */
  constructor(phase, message, {
    command = '',
    exitCode = -1,
    stdout = '',
    stderr = '',
    durationMs = 0,
    hint = '',
    nextAction = '',
    recoverable = true,
  } = {}) {
    super(message);
    this.name = 'ReleaseError';
    this.phase = phase;
    this.command = command;
    this.exitCode = exitCode;
    this.stdout = stdout;
    this.stderr = stderr;
    this.durationMs = durationMs;
    this.hint = hint;
    this.nextAction = nextAction;
    this.recoverable = recoverable;
  }

  /** Output structured JSON error block to stdout (LLM-parseable). */
  printStructured() {
    const payload = {
      release_error: true,
      phase: this.phase,
      message: this.message,
      command: this.command,
      exitCode: this.exitCode,
      durationMs: this.durationMs,
      stdout: truncate(this.stdout),
      stderr: truncate(this.stderr),
      hint: this.hint || HINTS[this.phase] || '',
      recoverable: this.recoverable,
      nextAction: this.nextAction || '',
    };
    console.log(); // blank line before
    console.log(JSON.stringify(payload, null, 2));
    console.log(); // blank line after
  }
}

/**
 * Truncate a string to MAX_OUTPUT_LENGTH characters.
 * Appends truncation marker if truncated.
 */
function truncate(str) {
  if (!str) return '';
  if (str.length <= MAX_OUTPUT_LENGTH) return str;
  return str.slice(0, MAX_OUTPUT_LENGTH) +
    `\n... [truncated, ${str.length - MAX_OUTPUT_LENGTH} more chars]`;
}

/**
 * Execute a shell command synchronously.
 *
 * @param {string} cmd - The command to execute
 * @param {string} phase - Phase identifier for error context
 * @param {object} opts
 * @param {number} [opts.timeout] - Timeout in ms
 * @param {boolean} [opts.inherit] - If true, use stdio:'inherit' (user sees live output)
 * @param {string} [opts.hint] - Override default hint
 * @param {boolean} [opts.recoverable] - Whether this phase can be retried
 * @param {string} [opts.nextAction] - Recommended next action
 * @param {string} [opts.cwd] - Working directory (default: root)
 * @returns {{ stdout: string, stderr: string, durationMs: number }}
 * @throws {ReleaseError}
 */
function run(cmd, phase, opts = {}) {
  const {
    timeout = TIMEOUTS.default,
    inherit = false,
    hint = '',
    recoverable = true,
    nextAction = '',
    cwd = root,
  } = opts;

  const stdioMode = inherit ? 'inherit' : 'pipe';
  const start = Date.now();

  try {
    const stdout = execSync(cmd, {
      encoding: 'utf8',
      timeout,
      stdio: stdioMode,
      cwd,
      windowsHide: true,
    });
    return {
      stdout: stdout || '',
      stderr: '',
      durationMs: Date.now() - start,
    };
  } catch (e) {
    const durationMs = Date.now() - start;
    const killed = e.killed || false;
    const exitCode = e.status !== null && e.status !== undefined
      ? e.status
      : (killed ? -1 : -2);

    const errMsg = killed
      ? `Command timed out (${timeout}ms): ${cmd}`
      : `Command failed (exit ${exitCode}): ${cmd}`;

    throw new ReleaseError(phase, errMsg, {
      command: cmd,
      exitCode,
      stdout: inherit ? '[stdio:inherit — output shown on screen]' : String(e.stdout || ''),
      stderr: inherit ? '[stdio:inherit — output shown on screen]' : String(e.stderr || ''),
      durationMs,
      hint: hint || HINTS[phase] || '',
      recoverable,
      nextAction,
    });
  }
}

/**
 * Async sleep helper.
 */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ============================================================
// Helpers
// ============================================================

/**
 * Parse command-line arguments.
 */
function parseArgs() {
  const args = process.argv.slice(2);
  let bump = 'patch';
  let customVersion = null;
  let serviceVersion = null;
  let dryRun = false;
  let yes = false;

  for (const arg of args) {
    if (arg === '--dry-run') dryRun = true;
    else if (arg === '--yes' || arg === '-y') yes = true;
    else if (arg === '--minor') bump = 'minor';
    else if (arg === '--major') bump = 'major';
    else if (arg.startsWith('--version=')) customVersion = arg.split('=')[1];
    else if (arg.startsWith('--service-version=')) serviceVersion = arg.split('=')[1];
  }

  return { bump, customVersion, serviceVersion, dryRun, yes };
}

/**
 * Bump a semver version string.
 * @param {string} version - e.g. "2.3.1"
 * @param {'patch'|'minor'|'major'} bump
 * @returns {string}
 */
function bumpVersion(version, bump) {
  const parts = version.split('.').map(Number);
  if (parts.length !== 3 || parts.some(isNaN)) {
    throw new ReleaseError('compute_version', `Invalid semver: ${version}`, {
      hint: 'package.json version 必须是 x.y.z 格式',
    });
  }
  const [major, minor, patch] = parts;
  switch (bump) {
    case 'major':
      return `${major + 1}.0.0`;
    case 'minor':
      return `${major}.${minor + 1}.0`;
    case 'patch':
    default:
      return `${major}.${minor}.${patch + 1}`;
  }
}

/**
 * Ask a yes/no question synchronously via readline.
 * @returns {Promise<boolean>}
 */
function askConfirm(prompt) {
  const rl = createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    rl.question(prompt, (answer) => {
      rl.close();
      const a = answer.trim().toLowerCase();
      resolve(a === 'y' || a === 'yes');
    });
  });
}

/**
 * Get the previous release tag (the highest vX.Y.Z), or '' if none.
 *
 * 不能用 `git describe --tags --abbrev=0`：发布 tag 打在 main 的 merge commit 上，
 * 而日常开发在 dev 上 —— merge commit 不是 dev 的祖先，describe 只看得见 dev 可达的
 * 旧 tag（本项目会一路退到 v2.1.4）。那会让 Release Notes 从 v2.1.4 起算（重复已发布
 * 内容），也会让「新版本号必须大于上一个 tag」的护栏对着错误的基线。
 * 直接按版本号排序取最高的 vX.Y.Z。
 */
function getPrevTag() {
  try {
    const out = execSync('git tag -l "v[0-9]*" --sort=-v:refname', {
      encoding: 'utf8',
      cwd: root,
      stdio: 'pipe',
      windowsHide: true,
    });
    const latest = out
      .split(/\r?\n/)
      .map((t) => t.trim())
      .find((t) => /^v\d+\.\d+\.\d+$/.test(t));
    return latest || '';
  } catch {
    return '';
  }
}

/**
 * 执行一个只取返回值的 git 命令，失败返回 ''。
 * 用于状态探测（rev-parse / tag -l）：探测失败不应抛 ReleaseError。
 */
function gitOut(cmd) {
  try {
    return execSync(cmd, {
      encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true,
    }).trim();
  } catch {
    return '';
  }
}

function readPackageJson() {
  return JSON.parse(readFileSync(pkgPath, 'utf8'));
}

/** `git diff --quiet` 风格命令：退出码 0 表示无差异。 */
function isCleanGitDiff(cmd) {
  try {
    execSync(cmd, { cwd: root, stdio: 'pipe', windowsHide: true });
    return true;
  } catch {
    return false;
  }
}

/** 保留文件原有的换行风格（Windows 工作区通常是 CRLF），避免 bump 提交里出现整文件换行 diff。 */
function detectEol(text) {
  return text.includes('\r\n') ? '\r\n' : '\n';
}

/**
 * 版本号的其他载体：backend/.env 的 APP_VERSION、server.config.example.json 的 env.APP_VERSION。
 * 状态栏「服务端版本」读的是前者，发版脚本必须一起维护，否则会出现安装包 2.5.1 但界面
 * 显示后端 2.5.0 的漂移。
 * @returns {Array<{ path: string, version: string }>}
 */
function readCarrierVersions() {
  const carriers = [];
  if (existsSync(backendEnvPath)) {
    const m = readFileSync(backendEnvPath, 'utf8').match(/^APP_VERSION=(.*)$/m);
    if (m) carriers.push({ path: backendEnvPath, version: m[1].trim() });
  }
  if (existsSync(backendServerConfigExamplePath)) {
    try {
      const cfg = JSON.parse(readFileSync(backendServerConfigExamplePath, 'utf8'));
      if (cfg?.env?.APP_VERSION) {
        carriers.push({ path: backendServerConfigExamplePath, version: String(cfg.env.APP_VERSION) });
      }
    } catch {
      // example 文件被改坏时不参与判重，交给 bump 阶段保持原样
    }
  }
  return carriers;
}

/**
 * 把版本号写进所有载体，返回原始内容用于失败回滚。
 * @param {string} newVersion
 * @returns {Map<string, string>} absolute path -> original content
 */
function writeCarrierVersions(newVersion) {
  const originals = new Map();
  for (const carrier of readCarrierVersions()) {
    const original = readFileSync(carrier.path, 'utf8');
    originals.set(carrier.path, original);
    if (carrier.path === backendEnvPath) {
      // 只替换值，保留行尾（CRLF/LF）
      writeFileSync(carrier.path, original.replace(/^APP_VERSION=[^\r\n]*/m, `APP_VERSION=${newVersion}`));
    } else {
      const cfg = JSON.parse(original);
      cfg.env.APP_VERSION = newVersion;
      const eol = detectEol(original);
      writeFileSync(carrier.path, JSON.stringify(cfg, null, 2).split('\n').join(eol) + eol);
    }
  }
  return originals;
}

function restoreCarrierVersions(originals) {
  for (const [path, content] of originals) {
    try {
      writeFileSync(path, content);
    } catch {
      // best effort
    }
  }
}

/**
 * 判断能否从上次失败处断点续跑（tag 已创建并推送在 main 上的状态）。
 *
 * 上一次发版若失败在 build / release / upload 阶段，bump 提交、dev→main 合并、
 * annotated tag 都已落地。按常规逻辑重跑会被「新版本号必须大于上一个 tag」挡住
 * （不带 --version 时则会算出下一个补丁号，白发一个版本）。只有下面条件全部成立
 * 才允许续跑：
 *   1. 显式指定 --version=<该 tag>
 *   2. tag 是最新 tag，且指向 main 当前提交
 *   3. package.json 的版本号等于该版本
 *   4. dev 与 tag 的树完全一致（同时覆盖 backend/.env 等版本载体与全部源码）
 *
 * 条件 1-3 不满足说明状态异常（抛带提示的错误）；条件 4 不满足说明发版后又改过
 * 源码/依赖 —— 必须发新版本号（正是 v2.3.x 事故的成因）。
 */
function detectResume(newVersion, customVersion, prevTag) {
  if (!customVersion) return false;
  const tag = `v${newVersion}`;
  if (gitOut(`git tag -l ${tag}`) !== tag) return false;
  if (prevTag !== tag) return false;

  const tagCommit = gitOut(`git rev-list -n 1 ${tag}`);
  const mainCommit = gitOut('git rev-parse main');
  if (!tagCommit || !mainCommit || tagCommit !== mainCommit) {
    throw new ReleaseError('compute_version',
      `Tag ${tag} exists but does not point at the current main HEAD`, {
      hint: `${tag} 指向的不是 main 当前提交，无法安全续跑。` +
        '若该 tag 是误建/过期产物，先删除（git tag -d 并删除远程同名 tag）再重跑；否则请换新版本号',
      recoverable: true,
      nextAction: `git tag -d ${tag} && git push origin :refs/tags/${tag}，或用新版本号重跑`,
    });
  }

  const pkgVersion = readPackageJson().version;
  if (pkgVersion !== newVersion) {
    throw new ReleaseError('compute_version',
      `package.json version ${pkgVersion} does not match resume target ${newVersion}`, {
      hint: 'package.json 与要续跑的版本不一致（上一次 bump 可能被手工改回）。' +
        '先把 package.json 改回该版本，或改用新版本号发布',
      recoverable: true,
      nextAction: `npm run release -- --version=<大于 ${tag.replace(/^v/, '')} 的版本号>`,
    });
  }

  if (!isCleanGitDiff(`git diff --quiet ${tag} dev`)) {
    throw new ReleaseError('compute_version',
      `dev 与 tag ${tag} 的内容不一致，不能续跑同一个版本`, {
      hint: '上一次发版之后源码/依赖有改动，产物会与 tag 对不上（v2.3.x 事故的成因）。' +
        '请改用新版本号发布修复',
      recoverable: true,
      nextAction: 'npm run release -- --version=<新版本号>',
    });
  }

  return true;
}

/**
 * 断点续跑时幂等补推 dev/main/tag —— 上一次可能停在 push 阶段。
 * 直接推 ref，不 checkout，避免在 dev/main 之间来回切。
 */
function ensureRefsPushed(newVersion) {
  run('git push origin dev', 'merge_and_tag', {
    timeout: 120000,
    hint: '检查网络连接；dev 推送失败会阻断续跑',
    nextAction: 'git push origin dev',
  });
  run('git push origin main', 'merge_and_tag', {
    timeout: 120000,
    hint: '检查网络连接；main 推送失败会阻断续跑',
    nextAction: 'git push origin main',
  });
  run(`git push origin v${newVersion}`, 'merge_and_tag', {
    timeout: 120000,
    hint: '检查网络连接；tag 推送失败会阻断续跑',
    nextAction: `git push origin v${newVersion}`,
  });
  console.log('  ✓ dev/main/tag refs pushed (idempotent)');
}

// ============================================================
// Phase 0: Preflight (TODO 2)
// ============================================================

function preflight() {
  console.log('[phase 0] Preflight checks...');

  // 1. Must be on dev branch
  const branch = execSync('git branch --show-current', {
    encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true,
  }).trim();
  if (branch !== 'dev') {
    throw new ReleaseError('preflight',
      `Must be on 'dev' branch, currently on '${branch}'`, {
      hint: 'git checkout dev 然后重新运行',
      recoverable: true,
      nextAction: 'git checkout dev && npm run release',
    });
  }
  console.log('  ✓ On dev branch');

  // 2. Working tree must be clean
  const status = execSync('git status --porcelain', {
    encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true,
  }).trim();
  if (status) {
    throw new ReleaseError('preflight',
      'Working tree is dirty; commit or stash changes first', {
      hint: `Dirty files:\n${status}`,
      recoverable: true,
      nextAction: 'git add . && git commit -m "..." 或 git stash',
    });
  }
  console.log('  ✓ Working tree clean');

  // 3. No package.json.bak residue
  if (existsSync(pkgBakPath)) {
    throw new ReleaseError('preflight',
      'package.json.bak found — historical residue from a crashed build', {
      hint: '手动删除 package.json.bak（build.mjs 简化后不会再产生此文件）',
      recoverable: true,
      nextAction: 'del package.json.bak',
    });
  }
  console.log('  ✓ No package.json.bak residue');

  // 4. gh must be authenticated
  try {
    execSync('gh auth status', {
      encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true,
    });
    console.log('  ✓ gh CLI authenticated');
  } catch {
    throw new ReleaseError('preflight',
      'gh CLI is not authenticated', {
      hint: '运行 gh auth login 进行认证',
      recoverable: true,
      nextAction: 'gh auth login',
    });
  }

  // 5. dev must be synced with remote
  try {
    const localHash = execSync('git rev-parse dev', {
      encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true,
    }).trim();
    const remoteHash = execSync('git rev-parse origin/dev', {
      encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true,
    }).trim();
    if (localHash !== remoteHash) {
      throw new ReleaseError('preflight',
        'dev branch has unpushed commits', {
        hint: 'git push origin dev 后再运行',
        recoverable: true,
        nextAction: 'git push origin dev',
      });
    }
    console.log('  ✓ dev synced with origin/dev');
  } catch (e) {
    if (e instanceof ReleaseError) throw e;
    throw new ReleaseError('preflight',
      'Cannot verify remote sync — origin/dev may not exist', {
      hint: '确保 remote origin 存在且 dev 分支已推送',
      recoverable: true,
      nextAction: 'git push -u origin dev',
    });
  }

  console.log('[phase 0] All preflight checks passed.\n');
}

// ============================================================
// Phase 1: Quality Gate (TODO 3)
// ============================================================

function qualityGate() {
  console.log('[phase 1] Running quality gate (npm run check:full)...');
  run('npm run check:full', 'quality_gate', {
    timeout: TIMEOUTS.qualityGate,
    inherit: true,
    recoverable: true,
    nextAction: '修复 lint/typecheck/单测/契约测试失败项后重新运行 npm run release',
  });
  console.log('[phase 1] Quality gate passed.\n');
}

// ============================================================
// Phase 2: Version Computation (TODO 4)
// ============================================================

/**
 * Compute the new version and generate release notes.
 * @param {object} parsedArgs - from parseArgs()
 * @returns {{ oldVersion: string, newVersion: string, notes: string, resume: boolean, serviceVersion: string|null, currentServiceVersion: string }}
 */
function computeVersion(parsedArgs) {
  const { bump, customVersion, serviceVersion } = parsedArgs;
  console.log('[phase 2] Computing version...');

  const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
  const oldVersion = pkg.version;
  const prevTag = getPrevTag();
  const currentServiceVersion = readCarrierVersions()[0]?.version || '(unknown)';

  // 前端（Electron app）与服务端（backend/）版本互相独立：只有 backend/ 自上一个
  // tag 以来有改动时，才需要用 --service-version 发布服务端版本。这里只提示，
  // 不自动推断 —— 自动 bump 会在「只改配置/依赖」时发出没有意义的版本号。
  const backendChanged = prevTag
    ? !isCleanGitDiff(`git diff --quiet ${prevTag} HEAD -- backend`)
    : true;
  if (backendChanged && !serviceVersion) {
    console.warn(
      `  ⚠ backend/ 自 ${prevTag || '首个版本'} 以来有改动，但未指定 --service-version；\n` +
      '    ── 服务端版本将保持不变。若本次要发布后端，请加：--service-version=X.Y.Z',
    );
  }

  // 双源一致性告警：bump 的基数是 **package.json 的当前值**，不是上一个 tag。
  // 手工把 version 提前提到目标版本（如 2.5.0）之后，不带参数跑默认 patch 会
  // 算出 2.5.1 —— 号段跳号、changelog 从更早的 tag 起算，且与「发布时双源一致」
  // 的规范相悖。这里只告警（手工预提版本是合法的动作），真正的护栏是下面的
  // 「必须比上一个 tag 新」硬校验。
  if (prevTag && compareVersions(oldVersion, prevTag) === -1) {
    console.warn(
      `  ⚠ package.json version (${oldVersion}) is OLDER than the last tag (${prevTag}).\n` +
      '    ── v2.3.x 的事故就是这样来的：tag 与 package.json 脱节后，产物名/latest.yml/\n' +
      '       应用内版本号都会停留在旧版本，用户端自更新会静默失效。\n' +
      `    ── 若本次就是想发布 ${oldVersion}，请显式指定：npm run release -- --version=${oldVersion}`,
    );
  } else if (prevTag && compareVersions(oldVersion, prevTag) === 1) {
    console.warn(
      `  ⚠ package.json version (${oldVersion}) is AHEAD of the last tag (${prevTag}) — ` +
      'version 被手工提前改过。\n' +
      `    ── 默认 patch 会从 ${oldVersion} 递增，得到 ${bumpVersion(oldVersion, bump)}（跳号）。\n` +
      `    ── 若本次发布就是 ${oldVersion}，请显式指定：npm run release -- --version=${oldVersion}`,
    );
  }

  const newVersion = customVersion || bumpVersion(oldVersion, bump);

  // Validate new version is valid semver
  if (!/^\d+\.\d+\.\d+$/.test(newVersion)) {
    throw new ReleaseError('compute_version', `Invalid version format: ${newVersion}`, {
      hint: '版本号必须是 x.y.z 格式',
    });
  }

  if (serviceVersion && !/^\d+\.\d+\.\d+$/.test(serviceVersion)) {
    throw new ReleaseError('compute_version', `Invalid service version format: ${serviceVersion}`, {
      hint: '--service-version 必须是 x.y.z 格式',
    });
  }

  // 断点续跑：tag 已创建、指向 main 且 dev 与之一致时，跳过 bump/merge/tag，
  // 直接从构建/发布阶段继续（见 detectResume 的注释）。
  if (detectResume(newVersion, customVersion, prevTag)) {
    console.log(`[phase 2] Resume mode: v${newVersion} 已存在且与 dev 一致。`);
    console.log('[phase 2]   跳过 bump/merge/tag，从构建/发布阶段继续。\n');
    return {
      oldVersion, newVersion, notes: generateNotes(prevTag), resume: true,
      serviceVersion: null, currentServiceVersion,
    };
  }

  // 硬校验：新版本号必须**高于**上一个 tag。
  // electron-updater 拿「应用内自报版本」与 feed 里 latest.yml 的 version 比较，
  // 一旦发布出去的版本号不大于上一版，所有用户都会被判定为「已是最新」而再也
  // 收不到更新（v2.3.0 / v2.3.1 就是这么发出去的：package.json 还停在 2.2.0）。
  if (prevTag) {
    const cmp = compareVersions(newVersion, prevTag);
    if (cmp === 0 || cmp === -1) {
      throw new ReleaseError('compute_version',
        `New version ${newVersion} is not newer than the last tag ${prevTag}`, {
        hint: '上一个 tag 之后的版本号必须更大。检查 package.json 的 version 是否被手工改过，' +
          '或用 --version= 指定一个更大的版本号',
        recoverable: true,
        nextAction: `npm run release -- --version=<version greater than ${prevTag.replace(/^v/, '')}>`,
      });
    }
  }

  // Tag conflict detection
  try {
    const existing = execSync(`git tag -l v${newVersion}`, {
      encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true,
    }).trim();
    if (existing) {
      throw new ReleaseError('compute_version',
        `Tag v${newVersion} already exists`, {
        hint: '检查版本号是否正确，或用 --version= 指定其他版本',
        recoverable: true,
        nextAction: 'npm run release -- --version=<different version>',
      });
    }
  } catch (e) {
    if (e instanceof ReleaseError) throw e;
    // git tag -l failure is unexpected but not a version conflict
  }

  const notes = generateNotes(prevTag);

  console.log(`[phase 2] Version: ${oldVersion} → ${newVersion}`);
  if (prevTag) console.log(`[phase 2] Previous tag: ${prevTag}`);
  console.log('[phase 2] Release notes generated.\n');

  return { oldVersion, newVersion, notes, resume: false, serviceVersion, currentServiceVersion };
}

/**
 * Generate release notes from commit log since the previous tag.
 * Categorizes by conventional commit prefix.
 * @param {string} prevTag - e.g. "v2.3.1"; '' = first release
 */
function generateNotes(prevTag) {
  let commits;

  if (prevTag) {
    try {
      commits = execSync(`git log ${prevTag}..HEAD --pretty=format:"%s"`, {
        encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true,
      }).trim();
    } catch {
      commits = '';
    }
  } else {
    // First release — include all commits
    try {
      commits = execSync('git log --pretty=format:"%s"', {
        encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true,
      }).trim();
    } catch {
      commits = '';
    }
  }

  if (!commits) return '_(no commits since previous tag)_';

  const fixes = [];
  const features = [];
  const refactors = [];
  const others = [];

  for (const line of commits.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (/^fix[\(:]/.test(trimmed)) fixes.push(trimmed);
    else if (/^feat[\(:]/.test(trimmed)) features.push(trimmed);
    else if (/^refactor[\(:]/.test(trimmed)) refactors.push(trimmed);
    else others.push(trimmed);
  }

  const sections = [];
  if (features.length) {
    sections.push('### ✨ New\n' + features.map((c) => `- ${c}`).join('\n'));
  }
  if (fixes.length) {
    sections.push('### 🐛 Fixes\n' + fixes.map((c) => `- ${c}`).join('\n'));
  }
  if (refactors.length) {
    sections.push('### 🔧 Changes\n' + refactors.map((c) => `- ${c}`).join('\n'));
  }
  if (others.length) {
    sections.push('### 📝 Others\n' + others.map((c) => `- ${c}`).join('\n'));
  }

  return sections.join('\n\n');
}

// ============================================================
// Confirmation (TODO 5)
// ============================================================

/**
 * Display the release plan and wait for user confirmation.
 * @param {object} [opts]
 * @param {boolean} [opts.autoConfirm] - true 时跳过交互（--yes）
 * @param {string|null} [opts.serviceVersion] - 本次要发布的服务端版本
 * @param {string} [opts.currentServiceVersion] - 当前服务端版本
 * @returns {Promise<boolean>} true if user confirmed
 */
async function showPlanAndWait(oldVersion, newVersion, notes, resume = false, {
  autoConfirm = false,
  serviceVersion = null,
  currentServiceVersion = '',
} = {}) {
  const sep = '='.repeat(60);

  console.log(`\n${sep}`);
  if (resume) {
    console.log(`Release Plan (RESUME):  v${newVersion}`);
  } else {
    console.log(`Release Plan:  v${oldVersion}  →  v${newVersion}`);
  }
  console.log(`Service version: ${serviceVersion ? `${currentServiceVersion} → ${serviceVersion}` : `keep ${currentServiceVersion}`}`);
  console.log(sep);

  if (resume) {
    console.log('\nSteps to execute:');
    console.log('  1. (resume) Skip bump / merge / tag — 已完成');
    console.log('  2. Re-push dev, main, and tag to origin (idempotent)');
    console.log('  3. Build (npm run build:win；产物已校验通过则跳过)');
    console.log('  4. Create GitHub Release + upload artifacts (draft 自动清理重建)');
    console.log('  5. Cleanup old release assets (keep latest 2)');
  } else {
    console.log('\nSteps to execute:');
    console.log('  1. Bump package.json' + (serviceVersion ? ' + service version carriers' : '（服务端版本不变）'));
    console.log('  2. Merge dev → main + annotated tag v' + newVersion);
    console.log('  3. Push dev, main, and tag to origin');
    console.log('  4. Build (npm run build:win)');
    console.log('  5. Create GitHub Release + upload artifacts');
    console.log('  6. Cleanup old release assets (keep latest 2)');
  }

  if (notes) {
    console.log(`\n${'-'.repeat(40)}`);
    console.log('Release Notes Preview:');
    console.log('-'.repeat(40));
    console.log(notes);
    console.log('-'.repeat(40));
  }

  if (autoConfirm) {
    console.log('\nAuto-confirmed (--yes).');
    return true;
  }

  const confirmed = await askConfirm('\nProceed with release? (y/n): ');

  if (!confirmed) {
    console.log('\nRelease cancelled. No changes made.');
    return false;
  }

  console.log();
  return true;
}

// ============================================================
// Phase 3a: Bump package.json + commit (TODO 6)
// ============================================================

function bumpPackageJson(newVersion, serviceVersion = null) {
  console.log('[phase 3a] Bumping version carriers...');

  const pkgText = readFileSync(pkgPath, 'utf8');
  const pkg = JSON.parse(pkgText);
  const pkgEol = detectEol(pkgText);

  // package.json = 前端（Electron app）版本，总是改。
  writeFileSync(pkgPath, JSON.stringify({ ...pkg, version: newVersion }, null, 2).split('\n').join(pkgEol) + pkgEol);

  // backend/.env、server.config.example.json = 服务端版本，只在显式 --service-version 时改。
  // 前端和服务端独立发版：服务端没改动时不应跟着前端跳版本号。
  const carriersBackup = serviceVersion ? writeCarrierVersions(serviceVersion) : new Map();

  const changedFiles = [pkgPath, ...carriersBackup.keys()]
    .map((p) => relative(root, p).split(/[/\\]/).join('/'));
  const quoted = changedFiles.map((f) => `"${f}"`).join(' ');

  if (serviceVersion) {
    console.log(`  ✓ Service version → ${serviceVersion}（${[...carriersBackup.keys()].map((p) => relative(root, p)).join(', ')}）`);
  } else {
    console.log('  ✓ Service version unchanged（未指定 --service-version）');
  }

  // Stage and commit
  try {
    run(`git add ${quoted}`, 'bump_version', {
      hint: 'git 操作失败，检查仓库状态',
    });
    // 已经是目标版本 = 没有东西可提交。用 `--version=<package.json 当前版本>` 时必然发生
    // （package.json 被手工预提过，见 RELEASE_GUIDE §1）：此时 `git commit` 会以
    // 「nothing to commit」退出 1，让整个发版中断在 bump 阶段 —— 但载体本来就已经一致，
    // 直接跳过即可。`git add` 顺便刷新了索引里的 stat 缓存，所以工作区依旧是干净的。
    const staged = run('git diff --cached --name-only', 'bump_version', {
      hint: 'git 操作失败，检查仓库状态',
    }).stdout.trim();
    if (!staged) {
      console.log(
        `[phase 3a] 版本载体已经是 ${newVersion}，没有需要提交的改动，跳过 bump 提交。\n`,
      );
      return;
    }
    run(`git commit -m "chore(release): bump version to ${newVersion}${serviceVersion ? ` (service ${serviceVersion})` : ''}"`, 'bump_version', {
      hint: 'git commit 失败',
    });
  } catch (e) {
    // Rollback: restore original carriers
    console.error('[phase 3a] Commit failed, rolling back version carriers...');
    writeFileSync(pkgPath, pkgText);
    restoreCarrierVersions(carriersBackup);
    try {
      execSync(`git checkout -- ${quoted}`, { cwd: root, stdio: 'pipe', windowsHide: true });
    } catch {
      // best-effort rollback
    }
    throw e;
  }

  console.log('[phase 3a] Version carriers bumped and committed.\n');
}

// ============================================================
// Phase 3b: Merge + Tag + Push (TODO 7)
// ============================================================

function mergeAndTag(newVersion) {
  console.log('[phase 3b] Merging dev → main, tagging, pushing...');

  // Push dev (carries the bump commit)
  run('git push origin dev', 'merge_and_tag', {
    timeout: 120000,
    hint: '检查网络连接；如失败可手动 git push origin dev 后重跑',
    nextAction: '先 git push origin dev，再用 --version=<package.json 当前版本> 重跑',
  });
  console.log('  ✓ Pushed dev to origin');

  // Switch to main
  run('git checkout main', 'merge_and_tag');
  console.log('  ✓ Switched to main');

  // Merge dev → main (fast-forward preferred)
  try {
    run('git merge dev', 'merge_and_tag', {
      hint: '存在合并冲突。git merge --abort 已自动执行，手动解决冲突后重试',
      nextAction: 'git merge --abort && 解决冲突后重新运行 npm run release',
    });
  } catch (e) {
    // Abort merge on failure
    try {
      execSync('git merge --abort', { cwd: root, stdio: 'pipe', windowsHide: true });
      console.log('  (merge aborted)');
    } catch {
      // may already be aborted
    }
    throw e;
  }
  console.log('  ✓ Merged dev → main');

  // Annotated tag on main
  run(`git tag -a v${newVersion} -m "v${newVersion}"`, 'merge_and_tag');
  console.log(`  ✓ Created annotated tag v${newVersion}`);

  // Push main
  run('git push origin main', 'merge_and_tag', {
    timeout: 120000,
    hint: '检查网络连接；push main 失败不影响 tag（已在本地）',
    nextAction: 'git push origin main && git push origin v' + newVersion,
  });
  console.log('  ✓ Pushed main to origin');

  // Push tag
  run(`git push origin v${newVersion}`, 'merge_and_tag', {
    timeout: 120000,
    hint: '检查网络连接；可手动推送 tag',
    nextAction: `git push origin v${newVersion}`,
  });
  console.log(`  ✓ Pushed tag v${newVersion} to origin`);

  console.log('[phase 3b] Merge + tag + push complete.\n');
}

// ============================================================
// Phase 4: Build (TODO 8)
// ============================================================

/**
 * 校验构建产物齐全且 latest.yml 的 path/version 与本次发布一致。
 * 不一致即抛错（阻断发布）；字段无法解析时只告警（electron-builder 正常输出不会走到）。
 */
function verifyArtifacts(newVersion) {
  const expectedExe = `Blank-Tool-Setup-${newVersion}.exe`;
  const exePath = join(buildDir, expectedExe);
  const blockmapPath = join(buildDir, `${expectedExe}.blockmap`);
  const ymlPath = join(buildDir, 'latest.yml');

  const missing = [];
  if (!existsSync(exePath)) missing.push(expectedExe);
  if (!existsSync(blockmapPath)) {
    console.warn(`  ⚠ Blockmap not found: ${expectedExe}.blockmap (non-fatal)`);
  }
  if (!existsSync(ymlPath)) missing.push('latest.yml');

  if (missing.length > 0) {
    const buildFiles = existsSync(buildDir) ? readdirSync(buildDir).join(', ') : '(build dir not found)';
    throw new ReleaseError('build',
      `Missing build artifacts: ${missing.join(', ')}`, {
      hint: `Expected: ${exePath}\nBuild directory contents: ${buildFiles}`,
      recoverable: true,
      nextAction: '检查 electron-builder 输出，修复后重新构建（tag 已存在时用 --version=<同版本> 续跑）',
    });
  }
  console.log(`  ✓ Artifact verified: ${expectedExe}`);
  console.log('  ✓ latest.yml found');

  const ymlContent = readFileSync(ymlPath, 'utf8');

  // path 必须与产物文件名一致
  const pathMatch = ymlContent.match(/^\s*path:\s*(.+)$/m);
  if (pathMatch) {
    const pathInYml = pathMatch[1].trim();
    if (pathInYml !== expectedExe) {
      throw new ReleaseError('build',
        `latest.yml path "${pathInYml}" does not match artifact "${expectedExe}"`, {
        hint: 'electron-builder 生成的 latest.yml 文件名与 artifactName 不一致，检查 package.json build.artifactName 配置',
        recoverable: true,
        nextAction: '检查 package.json 的 build.artifactName 配置',
      });
    }
    console.log(`  ✓ latest.yml path matches: ${pathInYml}`);
  } else {
    console.warn('  ⚠ Could not parse path field from latest.yml (non-fatal)');
  }

  // version 必须等于本次发布版本。
  //
  // 产物名、latest.yml 的 version、应用内自报的版本号**都取自 package.json.version**。
  // 只要 package.json 没被 bump（或 bump 后又被改回去），发出去的安装包会自报旧版本，
  // 而 latest.yml 也是旧版本 —— electron-updater 判定「已是最新」，所有用户静默收不到
  // 更新。v2.3.0 / v2.3.1 就是这样发出去的（package.json 停在 2.2.0）。只比对 path
  // 是看不见这种事故的：exe 名和 latest.yml 两边都叫 2.2.0，照样一致。
  const versionInYml = ymlContent.match(/^\s*version:\s*(.+)$/m);
  if (versionInYml) {
    const ymlVersion = versionInYml[1].trim().replace(/^["']|["']$/g, '');
    if (ymlVersion !== newVersion) {
      throw new ReleaseError('build',
        `latest.yml version "${ymlVersion}" does not match release v${newVersion}`, {
        hint: `产物版本号来自 package.json.version —— 它必须等于本次发布版本 ${newVersion}。` +
          '检查 package.json 是否已 bump（脚本的 bump 阶段会做），或是否被手工改过',
        recoverable: true,
        nextAction: `确认 package.json version 为 ${newVersion} 后重新运行 npm run release`,
      });
    }
    console.log(`  ✓ latest.yml version matches: ${ymlVersion}`);
  } else {
    console.warn('  ⚠ Could not parse version field from latest.yml (non-fatal)');
  }
}

/**
 * 断点续跑时判断能否直接复用 build/ 里已有的产物：
 * 三个文件齐全，且 latest.yml 的 path/version 都能解析并匹配。
 */
function canReuseBuild(newVersion) {
  const expectedExe = `Blank-Tool-Setup-${newVersion}.exe`;
  if (!existsSync(join(buildDir, expectedExe))) return false;
  if (!existsSync(join(buildDir, `${expectedExe}.blockmap`))) return false;
  const ymlPath = join(buildDir, 'latest.yml');
  if (!existsSync(ymlPath)) return false;
  try {
    const yml = readFileSync(ymlPath, 'utf8');
    const pathInYml = (yml.match(/^\s*path:\s*(.+)$/m) || [])[1]?.trim();
    const versionInYml = (yml.match(/^\s*version:\s*(.+)$/m) || [])[1]?.trim().replace(/^["']|["']$/g, '');
    return pathInYml === expectedExe && versionInYml === newVersion;
  } catch {
    return false;
  }
}

function build(newVersion, { reuseIfVerified = false } = {}) {
  console.log('[phase 4] Building...');

  if (reuseIfVerified && canReuseBuild(newVersion)) {
    console.log('  ✓ 已存在校验通过的构建产物，跳过重新构建（断点续跑）');
  } else {
    // Switch back to dev for building
    run('git checkout dev', 'build');
    console.log('  ✓ Switched back to dev');

    // Run the build
    console.log('  Running npm run build:win (this may take several minutes)...');
    run('npm run build:win', 'build', {
      timeout: TIMEOUTS.build,
      inherit: true,
      recoverable: true,
      nextAction: `修复构建问题后重跑：npm run release -- --version=${newVersion}（tag 已存在时自动断点续跑；若改过源码请改用新版本号）`,
    });
    console.log('  ✓ Build completed');
  }

  verifyArtifacts(newVersion);

  // Clean old build artifacts in build/ directory
  const files = readdirSync(buildDir);
  let cleaned = 0;
  for (const file of files) {
    if ((file.endsWith('.exe') || file.endsWith('.blockmap')) && !file.includes(newVersion)) {
      console.log(`  [clean] Removing old artifact: ${file}`);
      unlinkSync(join(buildDir, file));
      cleaned++;
    }
  }
  if (cleaned > 0) {
    console.log(`  ✓ Cleaned ${cleaned} old build artifact(s)`);
  }

  console.log('[phase 4] Build complete.\n');
}

// ============================================================
// Phase 5: Create GitHub Release (TODO 9)
// ============================================================

/**
 * Upload a file to a GitHub release with retry logic.
 * @param {string} tag - e.g. "v2.3.2"
 * @param {string} filePath - Absolute path to the file
 */
async function uploadWithRetry(tag, filePath) {
  const fileName = filePath.split(/[/\\]/).pop();
  const MAX_ATTEMPTS = 3;
  const RETRY_DELAY_MS = 5000;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      console.log(`  Uploading ${fileName} (attempt ${attempt}/${MAX_ATTEMPTS})...`);
      execSync(`gh release upload ${tag} "${filePath}"`, {
        encoding: 'utf8',
        timeout: TIMEOUTS.upload,
        stdio: 'inherit',
        cwd: root,
        windowsHide: true,
      });
      console.log(`  ✓ Uploaded ${fileName}`);
      return;
    } catch (e) {
      if (attempt < MAX_ATTEMPTS) {
        console.warn(`  ⚠ Upload attempt ${attempt}/${MAX_ATTEMPTS} failed: ${e.message}`);
        console.log(`  Retrying in ${RETRY_DELAY_MS / 1000}s...`);
        await sleep(RETRY_DELAY_MS);
      } else {
        throw new ReleaseError('upload',
          `Failed to upload ${fileName} after ${MAX_ATTEMPTS} attempts`, {
          command: `gh release upload ${tag} "${filePath}"`,
          exitCode: e.status || -1,
          stdout: String(e.stdout || ''),
          stderr: String(e.stderr || ''),
          hint: '检查网络连接；可安全重跑（同版本 draft 会自动清理）',
          recoverable: true,
          nextAction: `检查网络后重跑：npm run release -- --version=${tag.replace(/^v/, '')}（自动断点续跑）`,
        });
      }
    }
  }
}

async function createRelease(newVersion, notes) {
  console.log('[phase 5] Creating GitHub Release...');
  const tag = `v${newVersion}`;

  // Check for existing draft / release with same tag
  try {
    const viewResult = execSync(`gh release view ${tag} --json isDraft,name,tagName`, {
      encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true,
    });
    const release = JSON.parse(viewResult);
    console.log(`  Found existing release: ${release.tagName} (draft=${release.isDraft})`);
    if (release.isDraft) {
      console.log(`  Removing stale draft: ${tag}`);
      execSync(`gh release delete ${tag} --yes`, {
        cwd: root, stdio: 'inherit', windowsHide: true,
      });
      console.log('  ✓ Stale draft removed');
    } else {
      throw new ReleaseError('release',
        `Published release ${tag} already exists`, {
        hint: '使用不同的版本号（--version=）',
        recoverable: false,
        nextAction: 'npm run release -- --version=<newer version>',
      });
    }
  } catch (e) {
    if (e instanceof ReleaseError) throw e;
    // Release not found — expected, proceed
  }

  // Create empty draft release (no assets yet, to avoid timeout on large uploads)
  const notesFile = join(buildDir, '.release-notes.tmp');
  writeFileSync(notesFile, notes, 'utf8');
  try {
    run(`gh release create ${tag} --title "${tag}" --notes-file "${notesFile}" --draft`, 'release', {
      timeout: 120000,
      hint: '检查 GitHub 权限或网络连接',
      recoverable: true,
      nextAction: '检查 gh auth status 和网络连接',
    });
  } finally {
    try { unlinkSync(notesFile); } catch { /* cleanup */ }
  }
  console.log(`  ✓ Draft release created: ${tag}`);

  // Upload artifacts one by one (exe gets retry, others together)
  const exePath = join(buildDir, `Blank-Tool-Setup-${newVersion}.exe`);
  const blockmapPath = join(buildDir, `Blank-Tool-Setup-${newVersion}.exe.blockmap`);
  const ymlPath = join(buildDir, 'latest.yml');

  // Upload exe with retry
  await uploadWithRetry(tag, exePath);

  // Upload blockmap + latest.yml —— 各自重试（与 exe 同样的 3 次 / 间隔 5 秒）。
  // 早期版本把这两个文件合并成一次 `gh release upload` 上传且不重试，与文档里
  // 「上传自动重试 3 次」的描述不符：网络抖动时会直接失败在这里。
  const supportingFiles = [blockmapPath, ymlPath].filter((p) => existsSync(p));
  for (const file of supportingFiles) {
    await uploadWithRetry(tag, file);
  }
  if (supportingFiles.length > 0) {
    console.log(`  ✓ Uploaded ${supportingFiles.length} supporting file(s)`);
  }

  // Publish the release (remove draft status)
  run(`gh release edit ${tag} --draft=false`, 'release', {
    timeout: 60000,
    hint: '检查 GitHub 权限；release 已创建，手动 publish: gh release edit ' + tag + ' --draft=false',
  });
  console.log(`  ✓ Release published: ${tag}`);

  console.log('[phase 5] Release created and published.\n');
}

// ============================================================
// Phase 6: Cleanup Old Assets (TODO 10)
// ============================================================

function cleanupOldAssets(newVersion) {
  console.log('[phase 6] Cleaning up old release assets...');

  // Get all releases
  let releases;
  try {
    const listResult = run('gh release list --json tagName,name,createdAt --limit 200', 'cleanup', {
      timeout: 30000,
    });
    releases = JSON.parse(listResult.stdout);
  } catch (e) {
    if (e instanceof ReleaseError) {
      console.warn('  ⚠ Could not list releases, skipping cleanup');
    }
    return;
  }

  if (!Array.isArray(releases) || releases.length === 0) {
    console.log('  No releases to clean up.');
    console.log('[phase 6] Cleanup complete (nothing to do).\n');
    return;
  }

  // Filter to valid semver tags (vX.Y.Z)
  const semverRe = /^v\d+\.\d+\.\d+$/;
  const versioned = releases
    .filter((r) => semverRe.test(r.tagName))
    .sort((a, b) => {
      const [am, an, ap] = a.tagName.replace('v', '').split('.').map(Number);
      const [bm, bn, bp] = b.tagName.replace('v', '').split('.').map(Number);
      if (am !== bm) return bm - am;
      if (an !== bn) return bn - an;
      return bp - ap;
    });

  if (versioned.length <= 2) {
    console.log(`  Only ${versioned.length} versioned release(s), no cleanup needed.`);
    console.log('[phase 6] Cleanup complete.\n');
    return;
  }

  // Keep latest 2, clean the rest
  const toClean = versioned.slice(2);
  console.log(`  Keeping latest 2: ${versioned[0]?.tagName}, ${versioned[1]?.tagName}`);
  console.log(`  Will clean assets from ${toClean.length} older release(s)...`);

  let deleted = 0;
  for (const release of toClean) {
    try {
      // Get assets via GitHub API
      const apiResult = execSync(
        `gh api repos/:owner/:repo/releases/tags/${release.tagName} --jq ".assets[] | select(.name | endswith(\\".exe\\") or endswith(\\".blockmap\\")) | .name"`,
        { encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true, timeout: 30000 },
      ).trim();

      if (!apiResult) continue;

      const assetNames = apiResult.split('\n').filter(Boolean);
      for (const name of assetNames) {
        console.log(`  Deleting: ${release.tagName}/${name}`);
        try {
          execSync(`gh release delete-asset ${release.tagName} "${name}" --yes`, {
            cwd: root, stdio: 'pipe', windowsHide: true, timeout: 30000,
          });
          deleted++;
        } catch (delErr) {
          console.warn(`  ⚠ Failed to delete ${release.tagName}/${name}: ${delErr.message}`);
        }
      }
    } catch (e) {
      console.warn(`  ⚠ Could not process ${release.tagName}: ${e.message}`);
    }
  }

  console.log(`  ✓ Deleted ${deleted} old asset(s)`);
  console.log('[phase 6] Cleanup complete.\n');
}

// ============================================================
// Main (TODO 11)
// ============================================================

async function main() {
  const parsedArgs = parseArgs();

  console.log('╔══════════════════════════════════════════════════╗');
  console.log('║           Blank Tool Release Script             ║');
  console.log('╚══════════════════════════════════════════════════╝');
  console.log();

  if (parsedArgs.dryRun) {
    console.log('>>> DRY RUN MODE — no changes will be made <<<\n');
  }

  // ---- Phase 0: Preflight (always runs) ----
  preflight();

  // ---- Phase 2: Version computation (always runs; also detects resume) ----
  const { oldVersion, newVersion, notes, resume, serviceVersion, currentServiceVersion } = computeVersion(parsedArgs);

  // ---- Dry-run stops here ----
  if (parsedArgs.dryRun) {
    console.log('─'.repeat(60));
    console.log(`Version:       ${oldVersion} → ${newVersion}`);
    console.log(`Mode:          ${resume ? 'RESUME（tag 已存在，跳过 bump/merge/tag）' : 'normal'}`);
    console.log(`Service:       ${resume ? `keep ${currentServiceVersion}` : serviceVersion ? `${currentServiceVersion} → ${serviceVersion}` : `keep ${currentServiceVersion}`}`);
    console.log(`Bump type:     ${parsedArgs.customVersion ? 'custom' : parsedArgs.bump}`);
    console.log(`Tag:           v${newVersion}`);
    console.log(`Prev tag:      ${getPrevTag() || '(none — first release)'}`);
    console.log(`Release Notes:`);
    console.log(notes || '  (no commits since previous tag)');
    console.log('─'.repeat(60));
    console.log('\n>>> Dry-run complete. No changes made. <<<');
    return;
  }

  // ---- Phase 1: Quality gate ----
  qualityGate();

  // ---- Confirmation ----
  const confirmed = await showPlanAndWait(oldVersion, newVersion, notes, resume, {
    autoConfirm: parsedArgs.yes,
    serviceVersion: resume ? null : serviceVersion,
    currentServiceVersion,
  });
  if (!confirmed) return;

  if (resume) {
    // ---- 断点续跑：跳过 bump / merge / tag（tag 已存在），幂等补推 refs ----
    console.log('[resume] Tag 已存在，跳过 bump/merge/tag；补推 dev/main/tag...\n');
    ensureRefsPushed(newVersion);
  } else {
    // ---- Phase 3a: Bump version carriers ----
    bumpPackageJson(newVersion, serviceVersion);

    // ---- Phase 3b: Merge + Tag + Push ----
    mergeAndTag(newVersion);
  }

  // ---- Phase 4: Build（续跑且产物已校验通过时跳过构建） ----
  build(newVersion, { reuseIfVerified: resume });

  // ---- Phase 5: Create Release ----
  await createRelease(newVersion, notes);

  // ---- Phase 6: Cleanup ----
  cleanupOldAssets(newVersion);

  console.log('╔══════════════════════════════════════════════════╗');
  console.log(`║  Release v${newVersion} completed successfully!  ║`);
  console.log('╚══════════════════════════════════════════════════╝');
}

// ============================================================
// Top-level error handler + finally
// ============================================================

main()
  .catch((e) => {
    if (e instanceof ReleaseError) {
      console.error(`\n[ERROR] Release failed at phase '${e.phase}': ${e.message}`);
      e.printStructured();
    } else {
      console.error('\n[FATAL] Unexpected error:', e.message);
      console.error(e.stack);
      // Output minimal structured JSON for unexpected errors
      console.log();
      console.log(JSON.stringify({
        release_error: true,
        phase: 'unknown',
        message: e.message,
        hint: 'Unexpected error — check the stack trace above',
        recoverable: false,
      }, null, 2));
      console.log();
    }
    // 不要在这里 process.exit(1)：那会让下面的 .finally 不再执行（失败后就不会
    // 切回 dev，与文档承诺不符，还会让下一次 preflight 直接失败）。设置退出码让
    // 进程自然退出即可。
    process.exitCode = 1;
  })
  .finally(() => {
    // Always try to switch back to dev branch
    try {
      const currentBranch = execSync('git branch --show-current', {
        encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true,
      }).trim();
      if (currentBranch !== 'dev') {
        console.log('\n[finally] Switching back to dev branch...');
        execSync('git checkout dev', {
          cwd: root, stdio: 'inherit', windowsHide: true,
        });
        console.log('[finally] Now on dev branch.');
      }
    } catch {
      // Best effort — if this fails, we're likely in a bad state anyway
      console.warn('[finally] Could not switch back to dev. You may need to do it manually.');
    }
  });
