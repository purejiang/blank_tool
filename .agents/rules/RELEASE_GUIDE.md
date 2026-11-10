# Electron 应用发布指南（本项目）

日常发版只用一条命令 `npm run release`（`scripts/release.mjs`）。脚本自带交互确认、结构化错误提示（phase / hint / nextAction / recoverable）与断点续跑。本文档只记录脚本不告诉你的事。

通用发版规范（版本号与 tag、质量门禁、Release Notes、旧版本清理、通用检查清单）见 [通用发版规范](./RELEASE_GENERAL.md)；分支策略见 [通用分支策略](./BRANCHING.md)。

## 1. 用法速查

```bash
npm run release                            # 默认 patch bump
npm run release -- --minor                 # minor bump
npm run release -- --major                 # major bump
npm run release -- --version=2.5.0         # 指定版本号；该 tag 已存在且可续跑时自动进入续跑模式
npm run release -- --version=2.6.0 --service-version=2.5.1   # 前端 2.6.0，同时发布服务端 2.5.1
npm run release -- --yes                   # 跳过交互确认（自动化/CI 用）
npm run release -- --dry-run               # 仅预览：计算版本号并生成 notes，在质量门禁之前退出，不做任何修改
```

**前端与服务端版本互相独立**：`package.json.version` / git tag 是前端（Electron app）版本；`backend/.env` 与 `server.config.example.json` 里的 `APP_VERSION` 是服务端版本（状态栏显示的就是它）。只有 `backend/` 自上一个 tag 以来有改动时，才用 `--service-version=X.Y.Z` 一起发布服务端版本；不指定则服务端版本保持不变。脚本会在「后端有改动但没给 `--service-version`」时打印告警，但不会自动推断。

前置条件（脚本 preflight 自动检查，不满足即阻断）：
- 在 dev 分支
- 工作区干净
- 无 package.json.bak 残留
- gh CLI 已认证
- dev 与 origin/dev 一致（比较的是本地 `origin/dev` 引用，**脚本不 fetch**；怀疑远程有新提交时先 `git fetch` 或 `git push origin dev`）

质量门禁会跑 `npm run check:full`，因此本机还需要能执行 `python -m pytest`（未安装会在门禁阶段失败，preflight 不检查这一项）。

> ⚠️ **`--version=` 也是「package.json 被手工提前改过」时的正解。** 默认 patch 的递增基数是
> **package.json 的当前值**，不是上一个 tag；所以手工把 version 提到 2.5.0 之后再跑不带参数的
> release，会发出 `v2.5.1`（跳号，changelog 从更早的 tag 起算）。脚本会在版本计算阶段打印版本
> 载体一致性告警，并且**在新版本号不大于上一个 tag 时直接阻断** —— 那种版本号一旦发出去，用户端
> 自更新会判定「已是最新」而永远收不到更新。（载体已经是目标版本时，bump 阶段会跳过提交，不会以
> 「nothing to commit」中断。）
>
> 这不是假想：v2.3.0 / v2.3.1 的 **tag 树里 `package.json` 至今仍是 `"version": "2.2.0"`**
> （`git show v2.3.1:package.json`），可这两个 Release 实际传的却是 `Blank-Tool-Setup-2.3.0.exe`
> / `-2.3.1.exe` —— 说明产物是从「另一个 package.json 已经 bump 过的 dev 工作区」构建出来的。
> 于是 **tag 与产物对不上**：`git checkout v2.3.1 && npm run build:win` 会打出 2.2.0 的安装包。
> （产物自身版本是对的，所以那两次的用户端自更新并没有因此失效；坏掉的是可复现性。）

### 1.1 断点续跑（build / release 阶段失败后重跑）

上一次发版如果失败在**构建、创建 Release 或上传**阶段，此时 bump 提交、dev→main 合并、annotated tag 都已经落地（push 可能部分失败，续跑会幂等补推）。直接按默认 patch 重跑会算出**下一个**版本号（如 2.5.1 → 2.5.2），等于白发一个版本、把旧 tag 变成孤儿。

正确做法是**带上同一个版本号重跑**：

```bash
npm run release -- --version=2.5.1
```

脚本按下述条件识别「可以续跑」，满足时跳过 bump / merge / tag，只做（幂等的）补推、质量门禁复检、构建（产物已校验通过则跳过）、发布与清理：

- 显式给了 `--version=<该 tag>`（不带参数不会自动猜）；
- 该版本 tag 存在、是最新 tag、且指向 **main 当前提交**；
- `package.json.version` 等于该版本；
- **dev 与 tag 的树完全一致**（`git diff --quiet vX.Y.Z dev` 为空，同时覆盖 `backend/.env` 等版本载体与全部源码）。

限制与例外：

- 为了修构建而**改过源码或依赖**时不能续跑 —— 产物会与 tag 对不上。脚本会明确拒绝并提示改用新版本号；这种情况请把修复作为下一个补丁版本发布（旧 tag 会变成「有 tag 无 Release」的孤儿，不影响用户自更新）。
- **tag 尚未创建**的失败（合并冲突、push dev 失败）不能走续跑：先 `git push origin dev`，再用 `--version=<package.json 当前版本>` 重跑 —— 不带参数会基于已 bump 的版本号再跳一号。
- tag 不指向 main、或载体版本不一致时，脚本抛错并给出处置建议（删 tag / 先统一载体 / 换新版本号）。
- 同一版本已经成功发布后再跑会报 `published release already exists`（不可恢复），只能换版本号。

## 2. 版本号与构建产物

前端版本与服务端版本互相独立，各自有自己的载体：

| 独立版本 | 载体 | 谁在用 |
|---|---|---|
| 前端（app） | git tag `vX.Y.Z` | Release 页面、可复现性 |
| 前端（app） | `package.json` 的 `version` | Electron `app.getVersion()`（自更新判断）、产物名、`latest.yml` 的 `version` |
| 服务端（service） | `backend/.env` 的 `APP_VERSION` | 状态栏「服务端版本」（渲染层通过 `app.version` handler 读取） |
| 服务端（service） | `backend/server.config.example.json` 的 `env.APP_VERSION` | 新环境拷贝 `server.config.json` 时的默认值 |

- 前端版本：`npm run release` 每次都会 bump（tag 在合并后创建）。
- 服务端版本：只有 `backend/` 有改动时才需要发；用 `--service-version=X.Y.Z` 更新上面两个文件并随 bump 提交，不指定则保持原值。服务端版本**不要求**等于前端版本号。

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

**产物名、`latest.yml` 的 `version`、应用内自报版本（`app.getVersion()`，用户端自更新用它比较）都来自 `package.json.version`**，所以它们必须等于 tag（去掉 `v`）。`npm run release` 已在构建阶段自动校验两项，任一不符即阻断：

1. `path` 与 exe 文件名一致；
2. `version` 与本次发布的版本号一致（只比对 path 看不出这类事故：package.json 没 bump 时，exe 名与 latest.yml 的 `version` 会一起停在旧版本，path 检查照样通过）。

字段存在但不一致即阻断；仅当 latest.yml 里**解析不到** `path` / `version` 字段时才降级为告警（electron-builder 正常输出不会走到这一步）。

手动发布时用 PowerShell 比对：

```powershell
Select-String -Pattern '^\s*(version|path|url):' build/latest.yml
Get-ChildItem build/*.exe
```

`version` 必须等于 tag 去掉 `v` 的版本号，exe 必须是 `Blank-Tool-Setup-X.Y.Z.exe`。对不上就是版本载体没 bump（见 §1 的 `--version=` 说明）。保持连字符命名，不要改成点号或空格。

构建命令：`npm run build:win` / `build:mac` / `build:linux`。**一键发布当前只构建 Windows（脚本固定执行 build:win）**，macOS/Linux 需手动构建。

## 3. 失败恢复地图

任一阶段失败时脚本输出结构化 JSON（phase / hint / nextAction / recoverable），按提示修复后重跑即可。**build / release / upload 阶段的失败用 `--version=<同版本>` 重跑（断点续跑，见 §1.1）**；其余阶段直接重跑。无论成功失败，脚本都会切回 dev 分支（失败时通过退出码标记失败，不会跳过后面的切分支逻辑）。

重跑前可对照下表确认"已经做到了哪一步"——`phase` 列就是 JSON 里那个字段的值（控制台打印的阶段编号是脚本内部的 phase 0/1/2/3a/3b…，与下表编号不一致，以 `phase` 标识符为准）。

| 阶段 | phase 标识符 | 做什么 | 失败时的状态与恢复 |
|---|---|---|---|
| 1. preflight 环境检查 | `preflight` | 检查分支、工作区干净、gh 认证、dev 同步 | 无副作用。直接重跑。 |
| 2. 版本计算 + notes 生成 | `compute_version` | 计算新版本号（版本载体一致性告警 + "必须比上一个 tag 新"硬校验），从 git log 生成 Release Notes；若识别到可续跑状态则标记 resume | 无副作用。tag 已存在时：同版本续跑用 `--version=<同版本>`；否则换更大的版本号。`--dry-run` 到此为止。 |
| 3. 质量门禁 `npm run check:full` | `quality_gate` | 运行 lint + typecheck + vitest + pytest 契约测试 + node:test 共享契约测试 | 无副作用。修复失败项后重跑。 |
| 4. 交互确认 | —（输 n 直接退出，不产生错误） | 展示版本号与 Release Notes，等待 y/n 确认；续跑模式会显示 RESUME | 无副作用。输 n 取消无任何变更。 |
| 5. bump 版本载体 + commit | `bump_version` | 更新 package.json（带 `--service-version` 时一并更新 backend/.env 与 server.config.example.json）并提交到 dev | 失败自动回滚版本载体。直接重跑。 |
| 6. merge + tag + push | `merge_and_tag` | 合并 dev→main，打 annotated tag，推送 dev/main/tag 到远程 | merge 冲突时脚本已自动 abort。**先看 tag 是否已创建**：未创建（合并失败 / push dev 失败）→ 先 `git push origin dev`，再用 `--version=<package.json 当前版本>` 重跑（默认 patch 会再跳一号）；已创建（push main/tag 失败）→ 用 `--version=<同版本>` 续跑，会幂等补推。 |
| 7. 构建 build:win + 产物校验 | `build` | 执行 npm run build:win，校验 exe/blockmap/latest.yml 完整性 + latest.yml 的 path/version 一致性 | commit 与 tag 已完成。仅环境问题（依赖/磁盘/杀软）→ `--version=<同版本>` 续跑（产物已完整时跳过构建）；改过源码 → 换新版本号。 |
| 8. 发布 draft → 上传 → publish | `release` / `upload` | 创建 draft Release，上传 exe/blockmap/latest.yml，发布（移除 draft 状态） | `--version=<同版本>` 续跑：同版本 draft 自动删除重建；三个资产各自上传失败自动重试 3 次（间隔 5 秒）。同名 Release 已发布则会明确拒绝。 |
| 9. 清理旧版本资产 | `cleanup` | 保留最新 2 个版本，清理更旧版本的 .exe / .blockmap 资产 | 本次发布已完成。清理失败不影响发布结果，手动 `gh release delete-asset` 处理。 |

几个排障时会碰到、但不在上表里的行为：

- **构建是在 dev 上做的**：脚本打完 tag（在 main）后 `git checkout dev` 再构建。因为 dev 刚被合并进 main，两者内容一致；但如果你在 tag 之后又往 dev 提交，产物就不再对应 tag 的那个提交了 —— 要严格对应就手动在 main 上构建。
- **续跑会重跑质量门禁**：即使上次已经通过，续跑仍会再跑一遍 `check:full`（保证当前依赖/环境下的门禁状态）；只有构建产物可以在「已校验通过」时跳过。
- **清理只认 `vX.Y.Z` 形式的 tag**：历史遗留的 `1.0.0` / `1.0.1`（无 `v` 前缀）不匹配，它们的资产不会被自动清理，需要时手动 `gh release delete-asset`。
- **清理只扫最近 200 个 Release**（`gh release list --limit 200`）：更老版本的资产不会被自动清理，需要时手动处理。
- **超时值**：质量门禁 20 分钟、构建 15 分钟、单次上传 10 分钟（见 `release.mjs` 的 `TIMEOUTS`）。慢盘/杀软环境下可能触发 `Command timed out (…)`，先排除环境因素，再按对应阶段恢复。
- Release Notes 由 conventional commits 自动生成（识别的前缀是 `feat` / `fix` / `refactor`，其余进 Others）。本仓库提交信息中英混用是常态，因此 notes 也允许中英混用，[通用发版规范](./RELEASE_GENERAL.md#4-创建-github-release) 里"统一语言"那条在本项目不强制。

## 4. 手动发布（备选）

一键发布完全不可用、需要分步执行时使用。**bump 必须在 dev 上提交、再合并到 main**——反过来会把 bump 提交落在 main 上，导致 dev 落后，下一次 `npm run release` 会被「必须比上一个 tag 新」挡死：

```bash
git checkout dev && git push origin dev
# 手动把 package.json、backend/.env 的 APP_VERSION、server.config.example.json 的 env.APP_VERSION 改成 X.Y.Z
git add package.json backend/.env backend/server.config.example.json
git commit -m "chore(release): bump version to X.Y.Z"
npm run check:full
git push origin dev
git checkout main && git merge dev && git push origin main
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
npm run build:win
gh release create vX.Y.Z "build/Blank-Tool-Setup-X.Y.Z.exe" "build/Blank-Tool-Setup-X.Y.Z.exe.blockmap" "build/latest.yml" --title "vX.Y.Z" --notes "..."
```

随后按 [通用发版规范](./RELEASE_GENERAL.md#5-旧版本清理) 清理旧版本资产。

手动路径**没有**脚本的任何自动校验（版本载体一致性、latest.yml 的 version/path），也没有断点续跑，所以 §5 清单里的校验必须真的跑一遍。更要紧的是**别漏掉把 bump 提交进 tag**：v2.3.0 / v2.3.1 的 tag 树里 `package.json` 至今还是 2.2.0（产物反而是对的），而这正是脚本 bump 阶段要替掉的手工步骤。

## 5. 检查清单（Electron 特有）

通用项见 [通用发版规范](./RELEASE_GENERAL.md#7-发布检查清单)。推荐 `npm run release` 一键完成，手动验证仅在一键发布失败或分步执行时使用。

- [ ] `npm run check:full` 通过（含 pytest 契约测试 + node:test 共享契约测试）
- [ ] 按 `docs/TEST_CASES.md` 第六节冒烟最小集（10 条）人工过一遍 —— UI 回归脚本覆盖不到
- [ ] `npm run build:win` 构建成功
- [ ] `latest.yml` 的 `path` 与实际 exe 文件名一致（连字符命名）
- [ ] `latest.yml` 的 `version` == tag 去掉 `v`（对不上说明 package.json 没 bump：产物会自报旧版本，用户端自更新再也收不到更新）
- [ ] `backend/.env` 的 `APP_VERSION`：后端有改动时已通过 `--service-version` 更新；后端无改动时保持原值（不要求等于前端版本）
- [ ] Release 已 publish（非 draft），且 exe + blockmap + latest.yml 三个文件都在
- [ ] 发布后验证：`gh release view vX.Y.Z --json isDraft,assets` 看状态与资产
- [ ] 旧版本 exe/blockmap 资产已清理