# Electron 应用发布指南（本项目）

日常发版只用一条命令 `npm run release`（`scripts/release.mjs`）。脚本自带交互确认、结构化错误提示（phase / hint / nextAction / recoverable）与安全重跑。本文档只记录脚本不告诉你的事。

通用发版规范（版本号与 tag、质量门禁、Release Notes、旧版本清理、通用检查清单）见 [通用发版规范](./RELEASE_GENERAL.md)；分支策略见 [通用分支策略](./BRANCHING.md)。

## 1. 用法速查

```bash
npm run release                            # 默认 patch bump
npm run release -- --minor                 # minor bump
npm run release -- --major                 # major bump
npm run release -- --version=2.5.0         # 指定版本号
npm run release -- --dry-run               # 仅预览：计算版本号并生成 notes，在质量门禁之前退出，不做任何修改
```

前置条件（脚本 preflight 自动检查，不满足即阻断）：
- 在 dev 分支
- 工作区干净
- 无 package.json.bak 残留
- gh CLI 已认证
- dev 与 origin/dev 一致

> ⚠️ **`--version=` 也是「package.json 被手工提前改过」时的正解。** 默认 patch 的递增基数是
> **package.json 的当前值**，不是上一个 tag；所以手工把 version 提到 2.5.0 之后再跑不带参数的
> release，会发出 `v2.5.1`（跳号，changelog 从更早的 tag 起算）。脚本会在版本计算阶段打印双源
> 一致性告警，并且**在新版本号不大于上一个 tag 时直接阻断** —— 那种版本号一旦发出去，用户端
> 自更新会判定「已是最新」而永远收不到更新。
>
> 这不是假想：v2.3.0 / v2.3.1 就是这样发出去的（tag 是 v2.3.x，而 tag 处的 `package.json`
> 仍是 `"version": "2.2.0"`），产物名、latest.yml 的 version、应用内自报版本全都停在 2.2.0。

## 2. 版本号与构建产物

版本号双源：git tag 与 package.json（详见 [通用发版规范](./RELEASE_GENERAL.md#1-版本号管理)）。发版时 `npm run release` 先 bump package.json 并提交，再打 annotated tag，两个来源在发布时保持一致。

`scripts/build.mjs` 直接读取 package.json.version，无注入、无 .bak：

```javascript
// build.mjs — 直接读 package.json.version（行号为撰写时快照）
const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
console.log(`[build] Version: ${pkg.version}`);
```

旧版曾用 git describe 注入并产生 package.json.bak——若工作目录残留手动删除即可，preflight 会检查该残留并阻断。

产物命名由 package.json 的 `build.artifactName = "Blank-Tool-Setup-${version}.${ext}"` 决定，输出到 `build/`：

| 文件 | 用途 | 是否上传 |
|---|---|---|
| `Blank-Tool-Setup-X.Y.Z.exe` | 安装包 | ✅ 上传 |
| `Blank-Tool-Setup-X.Y.Z.exe.blockmap` | 增量更新块映射 | ✅ 上传 |
| `latest.yml` | 自动更新清单 | ✅ 上传 |

**latest.yml 与自动更新**：electron-updater 按 latest.yml 的 path/url 下载资产，文件名不一致会 404；而它判断「有没有新版本」，用的是 latest.yml 里的 `version` 与**应用内自报的版本号**。

**产物名、`latest.yml` 的 `version`、应用内自报版本三者都来自 `package.json.version`**，所以它们必须等于 tag（去掉 `v`）。`npm run release` 已在构建阶段自动校验两项，任一不符即阻断：

1. `path` 与 exe 文件名一致；
2. `version` 与本次发布的版本号一致（只比对 path 是看不见「tag 与 package.json 脱节」这类事故的 —— 两边都叫 2.2.0 时照样“一致”）。

手动发布时用 PowerShell 比对：

```powershell
Select-String -Pattern '^\s*(version|path|url):' build/latest.yml
Get-ChildItem build/*.exe
```

`version` 必须等于 tag 去掉 `v` 的版本号，exe 必须是 `Blank-Tool-Setup-X.Y.Z.exe`。对不上就是 `package.json` 没 bump（见 §1 的 `--version=` 说明）。保持连字符命名，不要改成点号或空格。

构建命令：`npm run build:win` / `build:mac` / `build:linux`。**一键发布当前只构建 Windows（脚本固定执行 build:win）**，macOS/Linux 需手动构建。

## 3. 失败恢复地图

任一阶段失败时脚本输出结构化 JSON（phase / hint / nextAction / recoverable），按提示修复后重跑即可，重跑是安全的（同版本 draft 残留自动清理重建）。无论成功失败，脚本最终自动切回 dev 分支。重跑前可对照下表确认"已经做到了哪一步"——`phase` 列就是 JSON 里那个字段的值（控制台打印的阶段编号是脚本内部的，与下表编号不一致，以 `phase` 标识符为准）。

| 阶段 | phase 标识符 | 做什么 | 失败时的状态与恢复 |
|---|---|---|---|
| 1. preflight 环境检查 | `preflight` | 检查分支、工作区干净、gh 认证、dev 同步 | 无副作用。直接重跑。 |
| 2. 版本计算 + notes 生成 | `compute_version` | 计算新版本号（并做双源一致性告警 + "必须比上一个 tag 新"硬校验），从 git log 生成 Release Notes | 无副作用。tag 已存在或版本号没比上一个 tag 大时，换版本号（`--version=`）重跑。`--dry-run` 到此为止。 |
| 3. 质量门禁 npm run check | `quality_gate` | 运行 lint + typecheck + test | 无副作用。修复 lint/typecheck/test 后重跑。 |
| 4. 交互确认 | —（输 n 直接退出，不产生错误） | 展示版本号与 Release Notes，等待 y/n 确认 | 无副作用。输 n 取消无任何变更。 |
| 5. bump package.json + commit | `bump_version` | 更新 version 字段并提交到 dev | 失败自动回滚 package.json。直接重跑。 |
| 6. merge + tag + push | `merge_and_tag` | 合并 dev→main，打 annotated tag，推送 dev/main/tag 到远程 | merge 冲突时脚本已自动 abort——在 dev 解决冲突并推送后重跑。push main/tag 失败按 nextAction 手动推送（`git push origin main && git push origin vX.Y.Z`）或重跑。 |
| 7. 构建 build:win + 产物校验 | `build` | 执行 npm run build:win，校验 exe/blockmap/latest.yml 完整性 + latest.yml 的 path/version 一致性 | commit 与 tag 已完成。修复构建错误后重跑，脚本从构建阶段继续。 |
| 8. 发布 draft → 上传 → publish | `release` / `upload` | 创建 draft Release，上传 exe/blockmap/latest.yml，发布（移除 draft 状态） | draft 可能已创建、部分资产可能已上传。直接重跑：同版本 draft 自动删除重建；三个资产各自上传失败自动重试 3 次（间隔 5 秒）。 |
| 9. 清理旧版本资产 | `cleanup` | 保留最新 2 个版本，清理更旧版本的 .exe / .blockmap 资产 | 本次发布已完成。清理失败不影响发布结果，手动 `gh release delete-asset` 处理。 |

三个脚本行为没写在上表、但排障时会碰到：

- **构建是在 dev 上做的**：脚本打完 tag（在 main）后会 `git checkout dev` 再构建。因为 dev 刚被合并进 main，两者内容一致；但如果你在 tag 之后又往 dev 提交，产物就不再对应 tag 的那个提交了 —— 要严格对应就手动在 main 上构建。
- **清理只认 `vX.Y.Z` 形式的 tag**：历史遗留的 `1.0.0` / `1.0.1`（无 `v` 前缀）不匹配，它们的资产不会被自动清理，需要时手动 `gh release delete-asset`。
- Release Notes 由 conventional commits 自动生成（识别的前缀是 `feat` / `fix` / `refactor`，其余进 Others）。本仓库提交信息中英混用是常态，因此 notes 也允许中英混用，[通用发版规范](./RELEASE_GENERAL.md#4-创建-github-release) 里"统一语言"那条在本项目不强制。

## 4. 手动发布（备选）

一键发布完全不可用、需要分步执行时使用：

```bash
git checkout dev && git push origin dev
git checkout main && git merge dev
npm run check
# 手动更新 package.json 的 version 并提交
git add package.json && git commit -m "chore(release): bump version to X.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin main vX.Y.Z
npm run build:win
gh release create vX.Y.Z "build/Blank-Tool-Setup-X.Y.Z.exe" "build/Blank-Tool-Setup-X.Y.Z.exe.blockmap" "build/latest.yml" --title "vX.Y.Z" --notes "..."
```

随后按 [通用发版规范](./RELEASE_GENERAL.md#5-旧版本清理) 清理旧版本资产。

手动路径**没有**脚本的任何自动校验（版本号一致性、latest.yml 的 version/path），所以 §5 清单里的两项
`latest.yml` 校验必须真的跑一遍 —— v2.3.0 / v2.3.1 两次发版就是绕过脚本时漏掉了这一步。

## 5. 检查清单（Electron 特有）

通用项见 [通用发版规范](./RELEASE_GENERAL.md#7-发布检查清单)。推荐 `npm run release` 一键完成，手动验证仅在一键发布失败或分步执行时使用。

- [ ] `npm run build:win` 构建成功
- [ ] `latest.yml` 的 `path` 与实际 exe 文件名一致（连字符命名）
- [ ] `latest.yml` 的 `version` == tag 去掉 `v`（对不上说明 package.json 没 bump：产物会自报旧版本，用户端自更新再也收不到更新）
- [ ] Release 已上传三个文件（exe + blockmap + latest.yml）
- [ ] 旧版本 exe/blockmap 资产已清理