# 协作与自动化约定

## 凭据

- 访问令牌一律不入库。`.env`、`*.key`、`*.pem` 已在 `.gitignore` 中，提交前用 `git status --ignored` 复核。
- 优先使用 fine-grained token，权限按仓库按需授予（Contents / Issues / Pull requests），避免长期持有 `repo` 全权限的 classic token。
- 令牌若曾出现在聊天记录、日志或 PR 描述里，视为已泄露，立即在 GitHub 上撤销重发。

## AI / 自动化代理

本仓库会被 AI 代理读写，因此约定：

- 代理默认只在功能分支上提交，不直接向 `main` 推送。
- 代理不得自行合并 PR、不得删除分支或仓库、不得修改 GitHub 上的权限与密钥设置。
- 涉及删除文件、重写历史、修改 CI 的改动，需人工明确确认后再执行。

## 提交流程

1. 从 `main` 切出 `feat/` 或 `fix/` 分支。
2. 一次提交解决一件事，标题遵循 Conventional Commits。
3. 开 PR 前自查：有没有混入凭据、有没有多余文件、说明是否讲清了动机。
4. `main` 仅通过 PR 合入。
