# -

软件开发专用仓库。

## 目录结构

```
.
├── src/       # 源代码（当前为空，见"当前状态"）
├── scripts/   # 构建、部署等辅助脚本
├── tests/     # 测试
└── docs/
    └── adr/   # 架构决策记录，含索引与模板
```

## 当前状态

已定：目录约定、提交规范、分支约定、协作与代理操作规则（`CONTRIBUTING.md`）。

未定：技术栈、依赖管理、CI、本地运行命令。原因见 [ADR-0001](docs/adr/0001-defer-stack.md)：
在第一个功能目标明确之前不放任何构建配置，避免出现"骨架齐全但从未运行过"的假状态。

所有"为什么这么定"的记录集中在 [决策记录索引](docs/adr/README.md)。

## 作为 DSH 插件接入

仓库根目录同时是一个 DeepSeek Harness 插件包（`package.json` + `cordis.patch.yml` + `index.js`）。
装好之后 DSH 多出一个 `dingtalk_workbench` 工具，负责离线入库与查询：

| action | 作用 |
|---|---|
| `ingest` | 把导出的 NDJSON 逐行归一化写入 SQLite，按消息幂等 |
| `init-db` | 按 `workbench/db/schema.sql` 建表或升级结构 |
| `stats` | 报会话 / 消息 / 附件计数与最新一条时间 |
| `search` | 检索正文；3 个字符起走 FTS5 trigram，更短走子串扫描 |

本地目录安装：DSH → 插件 → 添加插件，填本仓库的绝对路径；装完在插件列表确认「钉钉数据底座」这一行，
再新开一个会话调用工具验证。从 GitHub 安装则填 `https://github.com/zhiweiwei8899-svg/-`。

依赖：入库与查询只用标准库（`sqlite3` / `json`），但需要一个带 `sqlite3` 的 Python 3。
插件按 `DINGTALK_WORKBENCH_PYTHON` → `py` / `python3` / `python` → DSH 自带运行时 的顺序探测。
Windows 上若 `python` 是 Microsoft Store 的占位程序（`python --version` 退出码 9009），
请装真 Python，或设 `DINGTALK_WORKBENCH_PYTHON` 指向解释器；检出目录可用 `DINGTALK_WORKBENCH_REPO` 覆盖。

数据库默认位置随安装形态变化：检出安装用 `workbench/workbench.db`（已在 `.gitignore`），
从 GitHub 作为包安装时用用户数据目录（Windows `%LOCALAPPDATA%\dsh-dingtalk-workbench\`，
其他平台 `$XDG_DATA_HOME` 或 `~/.local/share/`），避免写进 `node_modules` 被重装清理。
`DINGTALK_WORKBENCH_DB` 可指定任意路径；工具结果里始终回显实际使用的库文件。

不装插件也能用同一条链路：

```bash
python3 workbench/collector/ingest.py --action ingest --ndjson raw-events.ndjson
python3 workbench/collector/ingest.py --action stats
```

## 提交规范

采用 Conventional Commits：

```
feat: 新功能
fix:    缺陷修复
docs:   仅文档变更
refactor: 重构（不改变外部行为）
chore:  构建/杂项维护
```

单次提交只做一件事，标题控制在 50 字以内，必要时在正文说明动机与影响范围。

## 分支约定

- `main`：始终可用，受保护，仅通过 PR 合入
- `feat/<简述>`、`fix/<简述>`：功能与修复分支，合入后删除
