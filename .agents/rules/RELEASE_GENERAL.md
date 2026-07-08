# 通用发版规范

适用于任何使用 git + GitHub Releases 的技术栈项目。可以拷贝到你的仓库直接复用。

构建步骤因技术栈而异，用占位符标注。其他章节（分支、版本、Release、存储治理）与语言和框架无关。

---

## 1. 分支策略

```
dev   ← 日常开发，所有 commit 先到这里（feature / bugfix）
main  ← 主线分支，始终保持可发布状态；只从 dev 合并，不直接打 commit
```

- **dev**：功能开发、bug 修复、日常提交。所有工作流从这里开始。
- **main**：保持干净。只通过 `git merge dev` 更新，不直接在上面写代码。

### 发布前合并

```bash
git checkout main
git merge dev            # 默认 fast-forward，也可用 --no-ff 保留 merge 痕迹
git push origin main
```

---

## 2. 版本号管理

版本号完全由 **git tag** 决定。不要在项目元数据文件中维护发布版本。

### 格式

遵循 SemVer：`v<主版本>.<次版本>.<修订号>`，例如 `v2.1.0`。

### 打 Tag

必须使用 annotated tag（`-a` 参数），变更摘要会出现在 GitHub Release 的 tag 页面。

```bash
git tag -a vX.Y.Z -m "vX.Y.Z - 简短变更摘要"
```

**规则**：
- Tag **必须打在 main 分支上**，不要打在 dev 上。
- 推送 tag：`git push origin vX.Y.Z`（单独推送，不要混在分支推送里）。

---

## 3. 发布前质量门禁

合并 dev 到 main 后，在构建或打 tag 之前，必须运行全量质量检查。

```bash
<!-- 在此填入你的质量检查命令，例如：
     静态分析（lint）、类型检查（typecheck）、测试套件（test） -->
```

质量检查全部通过后，再继续后续步骤。

```bash
git checkout main
git merge dev
<!-- 全量质量检查 -->
git tag -a vX.Y.Z -m "..."
git push origin main vX.Y.Z
```

---

## 4. 构建

构建命令和产物因技术栈而异。

```bash
<!-- 在此填入你的构建命令 -->
```

### 产物清单

| 文件 | 用途 | 是否上传 |
|---|---|---|
| `<!-- 你的构建产物 -->` | `<!-- 描述 -->` | ✅ / ❌ |

`gh release create` 时只上传对外发布的资产。内部构建产物（debug 符号、覆盖率报告、中间文件等）不应出现在 Release 页面。

---

## 5. 创建 GitHub Release

```bash
# gh 命令的通用形式
gh release create vX.Y.Z <产物文件...> \
  --title "vX.Y.Z" \
  --notes "## vX.Y.Z

### 🐛 Fixes
- ...

### ✨ Changes
- ..."
```

### Release Notes 规范

- 使用中文或英文，保持统一，不要在同一份 changelog 中混用。
- 用 emoji 分类：🐛 Fixes、✨ New / Improved、🚀 Performance、📝 Docs。
- 每条单独一行，以 `-` 开头。
- 如有，提及相关联的 issue 编号。

---

## 6. 旧版本清理（GitHub 2GB 存储配额治理）

GitHub Release 的存储总上限为 **2GB**。旧版本的大体积资产会占满配额。

### 正确做法：只删资产，保留 Release 页面

```bash
# ✅ 删除指定资产，release 页面和 changelog 保留
gh release delete-asset vX.Y.Z "old-asset.bin" --yes
```

### 错误做法：删整个 Release

```bash
# ❌ 删了整条 release + git tag，版本历史永久丢失
gh release delete vX.Y.Z --yes --cleanup-tag
```

### 维护节奏

保留最新版本（完整资产），保留倒数第二个版本作为回滚备份。更旧的版本只删除其资产，保留 release 页面和 changelog 条目。

```
v2.1.0 ← 最新，完整保留
v2.0.9 ← 保留资产（回滚备用）
v2.0.8 ← 删除资产（只保留 release 页面和 changelog）
v2.0.7 ← 同上
...
```

---

## 7. 发布后

```bash
git checkout dev
```

切回开发分支，继续日常工作。

---

## 8. 检查清单（发布前逐项确认）

- [ ] `git checkout main && git merge dev` -- main 与 dev 同步
- [ ] 全量质量检查通过（lint / typecheck / test，占位符：`<!-- 填入质量检查命令 -->`）
- [ ] `git tag -a vX.Y.Z -m "..."` -- tag 已打在 main 分支上
- [ ] 构建成功（`<!-- 填入构建命令 -->`）
- [ ] `gh release create` -- 所有需要的资产均已上传
- [ ] 旧版本资产已清理（`gh release delete-asset`）
- [ ] `git checkout dev` -- 切回开发分支
