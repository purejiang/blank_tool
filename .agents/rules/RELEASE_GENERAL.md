# 通用发版规范

适用于任何使用 git + GitHub Releases 的技术栈项目，可拷贝到你的仓库直接复用。

分支策略见 [通用分支策略](./BRANCHING.md)，本文只讲发版本身的规范。构建与质量检查命令因技术栈而异：本仓库已就地填入实际命令（带「本项目」标注），拷到别的项目时替换这几处即可。

---

## 1. 版本号管理

### 格式：SemVer vX.Y.Z（如 v2.1.0）

### 双源版本号

版本号有两个载体——git tag 与项目元数据文件（如 package.json）。推荐做法：发版流程先更新元数据文件的版本号并提交，再打 tag，使两个来源在发布时保持一致。

> **本项目（Blank Tool）**：双源 = git tag 与 `package.json.version`，由 `npm run release` 统一维护，并在构建阶段校验产物名与 `latest.yml` 的 `version`。手工提前改过 `version` 时必须用 `--version=` 指定同一版本号 —— 理由与已发生的事故见 [发布指南](./RELEASE_GUIDE.md#1-用法速查)。

### 打 Tag

- 必须 annotated tag：`git tag -a vX.Y.Z -m "vX.Y.Z - 简短变更摘要"`
- tag 必须打在 main 分支（先完成 dev → main 合并），不要打在 dev 上
- 单独推送 tag：`git push origin vX.Y.Z`

---

## 2. 发布前质量门禁

- 合并 dev 到 main 后，构建或打 tag 之前必须通过全量质量检查（静态分析、类型检查、完整测试套件）

```bash
npm run check   # 本项目：lint（vue-tsc --noEmit）+ typecheck + vitest（单测 + 集成测试）
npm run test    # 仅测试；后端 handler 契约测试另跑 pytest tests/contracts/
```

- 若项目有一键发布脚本，质量门禁应内置于脚本自动执行，失败即阻断发布

---

## 3. 构建

```bash
npm run build:win     # 本项目一键发布只构建 Windows；mac/linux 见 RELEASE_GUIDE.md §2
```

### 产物清单

| 文件 | 用途 | 是否上传 |
|------|------|----------|
| `Blank-Tool-Setup-X.Y.Z.exe` | NSIS 安装包（X.Y.Z 取自 package.json.version） | ✅ |
| `Blank-Tool-Setup-X.Y.Z.exe.blockmap` | 增量更新块映射 | ✅ |
| `latest.yml` | 自动更新清单（其 `version` 必须等于 tag 去掉 `v`） | ✅ |

只上传对外发布的资产；内部构建产物（debug 符号、覆盖率报告、中间文件）不应出现在 Release 页面。

---

## 4. 创建 GitHub Release

```bash
gh release create vX.Y.Z <产物文件...> \
  --title "vX.Y.Z" \
  --notes "..."
```

- 大体积资产建议先创建 draft（`--draft`），上传完成后再发布
- 上传宜具备失败重试能力

### Release Notes 规范

- 统一语言（中文或英文，不混用）—— **本项目例外**：提交信息中英混用是常态，自动生成的 notes 也允许混用（见 [发布指南](./RELEASE_GUIDE.md#3-失败恢复地图)）
- emoji 分类：✨ New、🐛 Fixes、🔧 Changes、📝 Others
- 每条一行以 `-` 开头
- 提及相关 issue 号
- 如有自动化，notes 可由 conventional commits 前缀自动生成（本项目识别 `feat` / `fix` / `refactor`，其余归入 Others），但仍建议发布前人工审阅

---

## 5. 旧版本清理

GitHub 对**单个** Release 资产文件有 2 GiB 上限；旧版本的大体积资产还会持续占用仓库体积、克隆时间与下载流量，所以仍需定期清理。

### 正确做法：只删资产，保留 Release 页面

```bash
gh release delete-asset vX.Y.Z "old-asset.bin" --yes
```

### 错误做法：删整个 Release

```bash
gh release delete vX.Y.Z --yes --cleanup-tag
```

版本历史永久丢失。

### 维护节奏

最新两个版本资产完整保留（最新 + 回滚备用）；更旧版本删除 exe/块映射等大体积资产，保留 release 页面和 changelog。

```
v2.1.0 ← 最新，完整保留
v2.0.9 ← 保留资产（回滚备用）
v2.0.8 ← 删除资产，只留页面和 changelog
v2.0.7 ← 同上
...
```

---

## 6. 发布后

```bash
git checkout dev
```

切回开发分支继续日常工作。

---

## 7. 发布检查清单

- [ ] `git checkout dev && git push origin dev` -- dev 已推送远程
- [ ] `git checkout main && git merge dev` -- main 与 dev 已同步
- [ ] `git push origin main` -- main 已推送远程（手动路径最容易漏这一步）
- [ ] 全量质量检查通过（`npm run check`）
- [ ] `git tag -a vX.Y.Z -m "..."` -- tag 打在 main 且为 annotated
- [ ] `git push origin vX.Y.Z` -- tag 已单独推送
- [ ] 构建成功（`npm run build:win`）
- [ ] 版本号三处一致：tag / package.json.version / 产物名与 latest.yml 的 `version`
- [ ] `gh release create` -- Release 资产齐全
- [ ] 旧版本资产已清理（`gh release delete-asset`）
- [ ] `git checkout dev` -- 已切回开发分支