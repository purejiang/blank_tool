# Electron 应用发布指南（本项目）

通用发布流程（分支策略、版本号管理、发布前质量门禁、GitHub Release 创建、Release Notes 规范、旧版本清理、发布后步骤、通用检查清单）见 [通用发版规范](./RELEASE_GENERAL.md)。本文档仅记录与 Electron / electron-builder 相关的特有步骤。

---

## 1. 版本号注入

版本号完全由 git tag 决定（详见 [第 2 节 版本号管理](./RELEASE_GENERAL.md#2-版本号管理)）。本项目的构建脚本 `scripts/build.mjs` 在打包前自动执行版本注入：

```javascript
// 核心逻辑：git describe → 注入 package.json → 构建 → 恢复
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

> ⚠️ 如果 `package.json.bak` 残留（上次构建崩溃），会覆盖当前备份。CI 中途 kill 进程可能留下脏状态——`finally` 块确保恢复。

---

## 2. 构建

### 环境准备

- Node.js 18+
- 所有依赖已安装（`npm install`）

构建前请确保通用质量门禁通过（详见 [第 3 节 发布前质量门禁](./RELEASE_GENERAL.md#3-发布前质量门禁)）。

### 构建命令

```bash
npm run build:win    # Windows（输出 Setup.exe + blockmap + latest.yml）
npm run build:mac    # macOS
npm run build:linux  # Linux
```

### 构建产物

| 文件 | 用途 | 是否上传 |
|---|---|---|
| `Setup X.Y.Z.exe` | 安装包 | ✅ |
| `Setup X.Y.Z.exe.blockmap` | 增量更新块映射 | ✅ |
| `latest.yml` | 自动更新清单 | ✅ |

### latest.yml 文件名校验

> ⚠️ `latest.yml` 中的 `url` / `path` 字段必须与 GitHub Release 上实际资产的文件名**完全一致**，否则自动更新会 404。electron-builder 默认用连字符命名产物（`Blank-Tool-Setup-X.Y.Z.exe`）。

上传前校验 `latest.yml` 里的文件名与 `build/` 下实际 exe 文件名一致：

```bash
# 检查 latest.yml 里的文件名
grep -E '^\s*(url|path):' build/latest.yml

# 检查 build/ 下实际产物名
ls build/*.exe

# 两者必须完全一致；如不一致，修正 latest.yml（保持连字符）
```

### 上传产物

构建完成后，使用 `gh release create` 上传产物。命令格式见 [第 5 节 创建 GitHub Release](./RELEASE_GENERAL.md#5-创建-github-release)，上传文件为上述三个构建产物。

---

## 3. 一键发布脚本参考

以下脚本整合了版本注入、构建、latest.yml 修正、旧版本清理和 Release 创建，可作为自动化发布的参考实现：

```javascript
const version = execSync('git describe --tags --abbrev=0').toString().trim();
const platform = process.argv[2] || 'win';

// 1. 版本注入 + 构建
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

// 2. 校验 latest.yml 文件名与实际产物一致（electron-builder 默认连字符命名）
const latestYml = 'build/latest.yml';
if (existsSync(latestYml)) {
  // 无需替换；仅确认 latest.yml 里的文件名与 build/ 下 exe 一致
}

// 3. 删除旧版本 exe
const prevVersion = execSync('git tag --sort=-creatordate | sed -n "2p"').toString().trim();
if (prevVersion) {
  execSync(`gh release delete-asset ${prevVersion} "Setup.${prevVersion.replace(/^v/, '')}.exe" --yes`, { stdio: 'inherit' });
}

// 4. 创建 Release
const setupExe = `build/Setup ${version.replace(/^v/, '')}.exe`;
execSync(`gh release create ${version} "${setupExe}" "${setupExe}.blockmap" "${latestYml}" --title "${version}" --notes "See commits for details."`, { stdio: 'inherit' });
```

---

## 4. 检查清单（Electron 特有）

通用检查清单项见 [第 8 节 检查清单](./RELEASE_GENERAL.md#8-检查清单发布前逐项确认)，以下仅为本项目 Electron 特有项：

- [ ] `npm run build:win` — 构建成功
- [ ] `latest.yml` 文件名与 Release 实际资产名一致（保持连字符）
- [ ] `gh release create` — 三个文件全部上传（exe + blockmap + latest.yml）
- [ ] 旧版本 exe 已清理（`gh release delete-asset`）
