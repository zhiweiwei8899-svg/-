# 0003. 采纳"dws 主 + MinerU/RAGFlow 两件套 + 存量补录"的组合架构

- 状态：已接受
- 日期：2026-11
- 相关：ADR-0002（dws 主路线）、docs/tech-scan.md（选型调研）、docs/architecture.md

## 背景

ADR-0002 已确定以 dws 为主路线。本 ADR 把"主路线如何组队"定死：
采集分增量与存量两条，文件识别与知识库用两个专用组件，
工作台优先用官方 aitable，兜底用 CowAgent/LangBot。

## 决策

我们决定采用如下组合，职责边界见 docs/architecture.md：

- 群数据底座 = `dws` 全量实时（官方） + `im-mcp`/`chat-exporter` 历史补录（本机一次性）
- 文件识别 = `dws drive` 取件 → `MinerU` 解析
- 知识库 = `dws wiki` 同步 ↔ `RAGFlow` 向量库
- 千问 = DashScope 驱动 dws / Agent
- 工作台 = `dws aitable` 仪表盘（快）或 H5 微应用（钉钉内嵌）
- 兜底 = 授权出问题时切 `CowAgent` 或 `LangBot`

入库前统一归一化为 canonical schema（messages / attachments / kb_nodes），
不以任何工具的原始格式作为存储格式。

## 考虑过的方案

| 方案 | 优点 | 缺点 | 放弃原因 |
|------|------|------|----------|
| 只用 dws 一家 | 组件最少 | 无文件深度解析、无向量检索 | 覆盖不了文件识别与问答 |
| CowAgent 单栈全包 | 开箱即用、有后台 | 只收 @消息，非全量 | 达不到"群所有数据"底座要求 |
| 抓取工具做主数据源 | 历史全量 | 版本脆弱、合规风险 | 只做一次性补录 |
| 本组合（采纳） | 各司其职、可独立替换 | 组件多、需维护边界 | — |

## 影响

- 正面：任一组件失效可单点替换；增量与存量解耦；官方与灰色路径明确隔离。
- 代价 / 风险：运维面变大（dws + MinerU + RAGFlow + 数据库）；
  RAGFlow 资源占用较高；dws 尚未完全 GA。
- 需要一并改动的东西：落地后补 ETL 脚本与入库适配器；
  首次真实数据入库后回填 canonical schema 的实际字段差异。

## 如何验证这个决定是对的

- 观察信号：M1–M5 里程碑（见 architecture.md）按期达成；替换任一组件不导致schema变更。
- 复核时间：M2（存量入库）完成后复核一次，M4（知识库问答）完成后复核一次。
