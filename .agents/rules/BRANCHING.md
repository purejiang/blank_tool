# 通用分支策略

适用于任何使用 git 的项目，可以拷贝到你的仓库直接复用。

## 1. 分支模型

```
dev   ← 日常开发，所有 commit（feature / bugfix / docs）先到这里
main  ← 主线分支，始终保持可发布状态，只从 dev 合并，不直接提交
```

- **dev**：功能开发、bug 修复、日常提交，所有工作从这里开始。
- **main**：发布基线，只通过 `git merge dev` 更新，不直接写代码；任何时刻可从 main 打 tag 发版。

## 2. 分支纪律

- 所有开发必须在 `dev` 分支上进行，禁止在 main 上直接提交。
- `main` 只用于发版（`dev` → `main` 合并 + 打 tag），始终保持可发布状态。
- 开始工作前第一件事：`git branch --show-current`，如果不是 `dev` 立即 `git checkout dev`。
- 发版前 `dev` 必须先推送到远程，保证本地与远程基线一致。

## 3. 日常开发流程

```bash
git checkout dev
git add <文件>
git commit -m "<type>(<scope>): <摘要>"
git push origin dev
```

提交信息推荐 conventional commits（`feat` / `fix` / `refactor` / `docs` / `chore` 等前缀），便于发版时按前缀自动归类生成 release notes。

## 4. 发布前合并

```bash
git checkout main
git merge dev            # 默认 fast-forward，也可用 --no-ff 保留 merge 痕迹
git push origin main
```

合并完成后再打 tag；tag 必须打在 main 上。版本号与 tag 规范见 [通用发版规范](./RELEASE_GENERAL.md)。

## 5. 常见错误

| 错误 | 后果 | 正确做法 |
|---|---|---|
| 在 main 上直接提交 | 污染发布基线 | 先提交到 dev 再合并 |
| tag 打在 dev 上 | 发布基线不一致 | 合并到 main 后再打 tag |
| 发版前忘记推送 dev | 远程与本地基线不一致 | 先 `git push origin dev` |
| 合并冲突久拖不决 | main 无法推进 | 在 dev 上解决后重新合并 |