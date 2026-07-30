// ============================================================
// scripts/release.mjs — 一键发版全流程
//
// Usage:
//   node scripts/release.mjs                  # default patch bump
//   node scripts/release.mjs --minor          # minor bump
//   node scripts/release.mjs --major          # major bump
//   node scripts/release.mjs --version=2.5.0  # explicit version
//   node scripts/release.mjs --dry-run        # preview only
// ============================================================

import { execSync } from 'child_process';
import { readFileSync, writeFileSync, existsSync, unlinkSync, readdirSync } from 'fs';
import { resolve, dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { createInterface } from 'readline';

// ============================================================
// Constants
// ============================================================

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '..');
const pkgPath = resolve(root, 'package.json');
const pkgBakPath = resolve(root, 'package.json.bak');
const buildDir = resolve(root, 'build');
const MAX_OUTPUT_LENGTH = 50000;

const TIMEOUTS = {
  default: 60000,
  qualityGate: 300000,
  build: 600000,
  upload: 600000,
};

const HINTS = {
  preflight:
    '检查分支/工作区/认证状态：确保在 dev 分支、工作区干净、gh 已认证、dev 已推送远程',
  quality_gate:
    '修复 lint/typecheck/test 失败项，完成后重新运行 npm run release',
  compute_version:
    '检查 tag 是否已存在，或用 --version= 指定其他版本号',
  merge_and_tag:
    '检查网络连接，或手动 git push；如 merge 冲突，解决后重试',
  build:
    '检查 vite/electron-builder 构建错误；确保依赖已安装（npm install）',
  release:
    '检查 GitHub 权限和网络连接；同版本 draft 残留会自动清理',
  upload:
    '检查网络连接；可安全重跑（draft 会自动清理重建）',
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
  let dryRun = false;

  for (const arg of args) {
    if (arg === '--dry-run') dryRun = true;
    else if (arg === '--minor') bump = 'minor';
    else if (arg === '--major') bump = 'major';
    else if (arg.startsWith('--version=')) customVersion = arg.split('=')[1];
  }

  return { bump, customVersion, dryRun };
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
 * Get the previous git tag (if any).
 * Falls back to empty string if no tags exist.
 */
function getPrevTag() {
  try {
    return execSync('git describe --tags --abbrev=0', {
      encoding: 'utf8',
      cwd: root,
      stdio: 'pipe',
      windowsHide: true,
    }).trim();
  } catch {
    return '';
  }
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
  console.log('[phase 1] Running quality gate (npm run check)...');
  run('npm run check', 'quality_gate', {
    timeout: TIMEOUTS.qualityGate,
    inherit: true,
    recoverable: true,
    nextAction: '修复 lint/typecheck/test 失败项后重新运行 npm run release',
  });
  console.log('[phase 1] Quality gate passed.\n');
}

// ============================================================
// Phase 2: Version Computation (TODO 4)
// ============================================================

/**
 * Compute the new version and generate release notes.
 * @param {object} parsedArgs - from parseArgs()
 * @returns {{ oldVersion: string, newVersion: string, notes: string }}
 */
function computeVersion({ bump, customVersion }) {
  console.log('[phase 2] Computing version...');

  const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
  const oldVersion = pkg.version;

  const newVersion = customVersion || bumpVersion(oldVersion, bump);

  // Validate new version is valid semver
  if (!/^\d+\.\d+\.\d+$/.test(newVersion)) {
    throw new ReleaseError('compute_version', `Invalid version format: ${newVersion}`, {
      hint: '版本号必须是 x.y.z 格式',
    });
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

  const notes = generateNotes();

  console.log(`[phase 2] Version: ${oldVersion} → ${newVersion}`);
  console.log('[phase 2] Release notes generated.\n');

  return { oldVersion, newVersion, notes };
}

/**
 * Generate release notes from commit log since the previous tag.
 * Categorizes by conventional commit prefix.
 */
function generateNotes() {
  const prevTag = getPrevTag();
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
 * @returns {Promise<boolean>} true if user confirmed
 */
async function showPlanAndWait(oldVersion, newVersion, notes) {
  const sep = '='.repeat(60);

  console.log(`\n${sep}`);
  console.log(`Release Plan:  v${oldVersion}  →  v${newVersion}`);
  console.log(sep);

  console.log('\nSteps to execute:');
  console.log('  1. Bump version in package.json + commit');
  console.log('  2. Merge dev → main + annotated tag v' + newVersion);
  console.log('  3. Push dev, main, and tag to origin');
  console.log('  4. Build (npm run build:win)');
  console.log('  5. Create GitHub Release + upload artifacts');
  console.log('  6. Cleanup old release assets (keep latest 2)');

  if (notes) {
    console.log(`\n${'-'.repeat(40)}`);
    console.log('Release Notes Preview:');
    console.log('-'.repeat(40));
    console.log(notes);
    console.log('-'.repeat(40));
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

function bumpPackageJson(newVersion) {
  console.log('[phase 3a] Bumping package.json version...');

  const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));

  // Write updated package.json
  writeFileSync(pkgPath, JSON.stringify({ ...pkg, version: newVersion }, null, 2) + '\n');

  // Stage and commit
  try {
    run('git add package.json', 'bump_version', {
      hint: 'git 操作失败，检查仓库状态',
    });
    run(`git commit -m "chore(release): bump version to ${newVersion}"`, 'bump_version', {
      hint: 'git commit 失败',
    });
  } catch (e) {
    // Rollback: restore original package.json
    console.error('[phase 3a] Commit failed, rolling back package.json...');
    writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n');
    try {
      execSync('git checkout package.json', { cwd: root, stdio: 'pipe', windowsHide: true });
    } catch {
      // best-effort rollback
    }
    throw e;
  }

  console.log('[phase 3a] package.json bumped and committed.\n');
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
    nextAction: '检查网络后重新运行 npm run release（bump commit 已在 dev 上）',
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

function build(newVersion) {
  console.log('[phase 4] Building...');

  // Switch back to dev for building
  run('git checkout dev', 'build');
  console.log('  ✓ Switched back to dev');

  // Run the build
  console.log('  Running npm run build:win (this may take several minutes)...');
  run('npm run build:win', 'build', {
    timeout: TIMEOUTS.build,
    inherit: true,
    recoverable: true,
    nextAction: '修复构建错误后重新运行 npm run release（commit/tag 已完成，需重跑构建+发布部分）',
  });
  console.log('  ✓ Build completed');

  // Verify artifacts
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
      nextAction: '检查 electron-builder 输出，修复后重新构建',
    });
  }
  console.log(`  ✓ Artifact verified: ${expectedExe}`);
  console.log('  ✓ latest.yml found');

  // Verify latest.yml path field matches artifact filename
  const ymlContent = readFileSync(ymlPath, 'utf8');
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
          nextAction: '检查网络后重新运行 npm run release',
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

  // Upload blockmap + latest.yml
  const supportingFiles = [blockmapPath, ymlPath].filter((p) => existsSync(p));
  if (supportingFiles.length > 0) {
    const filesArg = supportingFiles.map((f) => `"${f}"`).join(' ');
    run(`gh release upload ${tag} ${filesArg}`, 'upload', {
      timeout: TIMEOUTS.upload,
      inherit: true,
      hint: '检查网络连接；可安全重跑',
      recoverable: true,
      nextAction: '检查网络后重新运行 npm run release',
    });
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
    const listResult = run('gh release list --json tagName,name,createdAt --limit 50', 'cleanup', {
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

  // ---- Phase 2: Version computation (always runs) ----
  const { oldVersion, newVersion, notes } = computeVersion(parsedArgs);

  // ---- Dry-run stops here ----
  if (parsedArgs.dryRun) {
    console.log('─'.repeat(60));
    console.log(`Version:       ${oldVersion} → ${newVersion}`);
    console.log(`Bump type:     ${parsedArgs.customVersion ? 'custom' : parsedArgs.bump}`);
    console.log(`Tag:           v${newVersion}`);
    console.log(`Prev tag:      ${getPrevTag() || '(none — first release)'}`);
    console.log(`Release Notes:`);
    console.log(notes || '  (no commits since previous tag)');
    console.log('─'.repeat(60));
    console.log('\n>>> Dry-run complete. No changes made. <<<');
    process.exit(0);
  }

  // ---- Phase 1: Quality gate ----
  qualityGate();

  // ---- Confirmation ----
  const confirmed = await showPlanAndWait(oldVersion, newVersion, notes);
  if (!confirmed) {
    process.exit(0);
  }

  // ---- Phase 3a: Bump package.json ----
  bumpPackageJson(newVersion);

  // ---- Phase 3b: Merge + Tag + Push ----
  mergeAndTag(newVersion);

  // ---- Phase 4: Build ----
  build(newVersion);

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

const originalBranch = (() => {
  try {
    return execSync('git branch --show-current', {
      encoding: 'utf8', cwd: root, stdio: 'pipe', windowsHide: true,
    }).trim();
  } catch {
    return '';
  }
})();

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
    process.exit(1);
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
