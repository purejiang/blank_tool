# Electron 应用发布规范

适用于 Electron + electron-builder + GitHub Releases 的桌面应用。不绑定特定项目，可作为模板直接复用。

---

## 1. 分支策略

```
dev   ← 日常开发，所有 commit 先到这里
main  ← 主线分支，只从 dev 合并，不直接打 commit
```

- **dev**：功能开发、bug 修复、日常提交
- **main**：始终保持可发布状态，只通过 `git merge dev` 更新

### 发布前合并

```bash
git checkout main
git merge dev          # 默认 fast-forward，也可以 --no-ff 保留 merge 痕迹
git push origin main
```

---

## 2. 版本号管理

版本号完全由 **git tag** 决定，不要在 `package.json` 里维护发布版本。

### 打 Tag

```bash
# 必须在 main 分支上
git checkout main
git tag -a vX.Y.Z -m "vX.Y.Z - 简短的版本说明"
git push origin vX.Y.Z
```

**规则**：
- 格式：`v<主版本>.<次版本>.<修订号>`（如 `v2.1.0`）
- tag **必须打在 main 上**，不要打在 dev 上
- annotation tag（`-a`）包含变更摘要，会出现在 GitHub Release 的 tag 页

### 版本号注入

如果使用 `git describe --tags` 自动获取版本号，构建脚本需要在打包前注入 `package.json`：

```javascript
// scripts/build.mjs 核心逻辑
const version = execSync('git describe --tags --abbrev=0').toString().trim().replace(/^v/, '');

// 备份原始 package.json
copyFileSync('package.json', 'package.json.bak');

// 注入版本
const pkg = JSON.parse(readFileSync('package.json', 'utf8'));
pkg.version = version;
writeFileSync('package.json', JSON.stringify(pkg, null, 2));

try {
  execSync('npx vite build', { stdio: 'inherit' });
  execSync('npx electron-builder --win', { stdio: 'inherit' });
} finally {
  // 恢复原始 package.json
  copyFileSync('package.json.bak', 'package.json');
  unlinkSync('package.json.bak');
}
```

> ⚠️ 构建过程中如果 `package.json.bak` 残留（上次崩溃），会覆盖当前备份。CI 中途 kill 进程可能留下脏状态——`finally` 块确保恢复。

---

## 3. 构建

### 环境准备

- Node.js 18+
- 所有依赖已安装（`npm install`）
- 运行 `npm run check`（lint + typecheck + test）通过

### Windows 构建

```bash
npm run build:win
# 输出: build/Blank Tool Setup X.Y.Z.exe
#       build/Blank Tool Setup X.Y.Z.exe.blockmap
#       build/latest.yml
```

### macOS / Linux

```bash
npm run build:mac
npm run build:linux
```

### 构建产物

| 文件 | 用途 | 是否上传 |
|---|---|---|
| `Setup X.Y.Z.exe` | 安装包 | ✅ |
| `Setup X.Y.Z.exe.blockmap` | 增量更新块映射 | ✅ |
| `latest.yml` | 自动更新清单 | ✅ |

> ⚠️ `latest.yml` 中的文件名可能包含连字符（`Blank-Tool-Setup`），GitHub 会将空格转为点号（`Blank.Tool.Setup`）。**上传前将 `latest.yml` 中的文件名修正为点号格式**，否则自动更新会 404。

```bash
# 修正 latest.yml 中的文件名
sed -i 's/Blank-Tool-Setup/Blank.Tool.Setup/g' build/latest.yml
# 或 PowerShell:
(Get-Content build/latest.yml) -replace 'Blank-Tool-Setup','Blank.Tool.Setup' | Set-Content build/latest.yml
```

---

## 4. 创建 GitHub Release

```bash
# 上传构建产物并创建 release
gh release create vX.Y.Z \
  "build/Setup X.Y.Z.exe" \
  "build/Setup X.Y.Z.exe.blockmap" \
  "build/latest.yml" \
  --title "vX.Y.Z" \
  --notes "## vX.Y.Z

### 🐛 Fixes
- ...

### ✨ Changes
- ..."
```

### Release Notes 规范

- 使用中文或英文，保持统一
- 用 emoji 分类：🐛 修复、✨ 新增/改进、🚀 性能、📝 文档
- 每条一行，用 `-` 开头
- 提及相关联的 issue 号（如有）

---

## 5. 旧版本清理（释放 GitHub 存储空间）

GitHub Release 总大小限制 **2GB**，旧版本 `.exe` 会占满配额。

### 正确做法：只删 exe

```bash
# ✅ 只删 exe 资产，release 页面和 changelog 保留
gh release delete-asset vX.Y.Z "Setup.X.Y.Z.exe" --yes
```

### 错误做法：删整个 release

```bash
# ❌ 删了整条 release + git tag，版本历史永久丢失
gh release delete vX.Y.Z --yes --cleanup-tag
```

### 维护节奏

每次新建 release 后，删除上一个旧版本的 exe（保留倒数第二个以防回滚需要）：

```
v2.1.0 ← 最新，完整保留
v2.0.9 ← 保留 exe（回滚备用）
v2.0.8 ← 删除 exe（只保留 release 页面和 changelog）
v2.0.7 ← 同上
...
```

---

## 6. 一键发布脚本

将上述流程整合为一个脚本 `scripts/release.mjs`：

```javascript
import { execSync } from 'child_process';
import { copyFileSync, readFileSync, writeFileSync, unlinkSync, existsSync } from 'fs';

const version = execSync('git describe --tags --abbrev=0').toString().trim();
const platform = process.argv[2] || 'win';

if (!version) {
  console.error('No git tag found. Run: git tag -a vX.Y.Z -m "..."');
  process.exit(1);
}

console.log(`[release] Version: ${version}, Platform: ${platform}`);

// 1. 构建
const pkgPath = 'package.json';
copyFileSync(pkgPath, pkgPath + '.bak');
const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
pkg.version = version.replace(/^v/, '');
writeFileSync(pkgPath, JSON.stringify(pkg, null, 2));

try {
  execSync('npx vite build', { stdio: 'inherit' });
  execSync(`npx electron-builder --${platform}`, { stdio: 'inherit' });
} finally {
  copyFileSync(pkgPath + '.bak', pkgPath);
  unlinkSync(pkgPath + '.bak');
}

// 2. 修正 latest.yml 文件名
const latestYml = 'build/latest.yml';
if (existsSync(latestYml)) {
  let content = readFileSync(latestYml, 'utf8');
  content = content.replace(/Setup-/g, 'Setup.');
  writeFileSync(latestYml, content);
}

// 3. 删除旧版本 exe
const prevVersion = execSync('git tag --sort=-creatordate | sed -n "2p"').toString().trim();
if (prevVersion) {
  console.log(`[release] Removing exe from ${prevVersion}...`);
  try {
    execSync(`gh release delete-asset ${prevVersion} "Setup.${prevVersion.replace(/^v/, '')}.exe" --yes`, { stdio: 'inherit' });
  } catch { /* 旧版本可能已经没有 exe */ }
}

// 4. 创建 Release
const setupExe = `build/Setup ${version.replace(/^v/, '')}.exe`;
console.log(`[release] Creating release ${version}...`);
execSync(`gh release create ${version} "${setupExe}" "${setupExe}.blockmap" "${latestYml}" --title "${version}" --notes "See commits for details."`, { stdio: 'inherit' });

console.log(`[release] Done: https://github.com/<owner>/<repo>/releases/tag/${version}`);
```

---

## 7. 检查清单

发布前走一遍：

- [ ] `git checkout main && git merge dev` — main 已同步
- [ ] `npm run check` — lint + typecheck + test 通过
- [ ] `git tag -a vX.Y.Z -m "..."` — tag 已打在 main 上
- [ ] `npm run build:win` — 构建成功
- [ ] `latest.yml` 文件名已修正为点号格式
- [ ] `gh release create` — 三个文件全部上传（exe + blockmap + latest.yml）
- [ ] 旧版本 exe 已清理（`gh release delete-asset`）
- [ ] `git checkout dev` — 切回开发分支
