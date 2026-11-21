# 架构：钉钉群数据底座（千问驱动）

> 决策依据：ADR-0002（dws 主路线）、ADR-0003（本组合采纳）。
> 选型证据与核实级别：docs/tech-scan.md。

## 一、组件与职责

| 层 | 组件 | 职责 | 部署位置 | 依赖 |
|----|------|------|----------|------|
| 采集·增量 | `dws`（官方 CLI） | `event consume` 订阅全部群/单聊消息；`chat` 消息搜索 | Linux 沙箱/服务器 | 企业管理员授权 |
| 采集·存量 | `im-mcp` 或 `dingtalk-chat-exporter` | 一次性导出本机加密库中的历史消息与附件 | **必须 Windows/Mac 本机** | 钉钉桌面客户端 |
| 处理·文件 | `MinerU` | PDF/Office/扫描件 → Markdown/JSON（OCR、表格、公式） | Linux | 无（模型随包） |
| 存储·知识库 | `RAGFlow` | 向量库 + 检索问答；文档解析 | Linux | Docker |
| 存储·结构化 | 本地 SQLite/Parquet（前期） | 消息、附件、会话的统一表 | Linux | 无 |
| 模型 | DashScope 千问 | 问答、摘要、抽取 | 云端 API | API Key |
| 应用·工作台 | `dws aitable` 仪表盘 / H5 微应用 | 钉钉内表格看板；必要时自建页面 | 钉钉内 | 企业授权 |
| 兜底 | `CowAgent` / `LangBot` | 授权不可用时：机器人 + 知识库 + Web 后台 | Linux | 机器人凭据 |

## 二、数据流

```
[本机 Windows/Mac]                    [Linux 服务器/沙箱]
dingtalk-chat-exporter ──JSON──┐
                              ├→ 统一入库(SQLite) → ETL(CSV/XLSX) → dws aitable 仪表盘
dws event consume ──NDJSON────┘         │
   (增量，实时)                          ├→ MinerU 解析附件 → RAGFlow 知识库
                                        └→ 千问(DashScope) 问答 / 摘要
dws wiki ←──双向同步──→ RAGFlow 知识库
```

三条数据链路互不阻塞，任何一条断掉其余仍可用。

## 三、统一数据模型（canonical，先定后写）

入库不直接使用任何工具的原始格式，先归一化，避免换工具即重建。

### messages（消息）

| 字段 | 类型 | 说明 |
|------|------|------|
| msg_id | TEXT PK | 全局唯一；原始无 ID 时用 `conv_id + sent_at + 内容哈希` 生成 |
| conv_id | TEXT | 会话 ID（群或单聊） |
| conv_type | TEXT | group / p2p |
| conv_name | TEXT | 群名或对方昵称 |
| sender_id | TEXT | 发送者 userId |
| sender_name | TEXT | 发送者显示名 |
| sent_at | TEXT (ISO8601) | 发送时间 |
| msg_type | TEXT | text / image / file / audio / video / card / system |
| text | TEXT | 文本内容；非文本消息留空 |
| raw_json | TEXT | 原始报文，保留取证与重解析能力 |

### attachments（附件）

| 字段 | 类型 | 说明 |
|------|------|------|
| att_id | TEXT PK | |
| msg_id | TEXT FK | 关联消息 |
| file_name | TEXT | |
| file_type | TEXT | 扩展名或 MIME |
| size_bytes | INTEGER | |
| local_path | TEXT | 本机/服务器落盘路径 |
| parsed_path | TEXT | MinerU 解析后的 Markdown 路径 |
| parse_status | TEXT | pending / done / failed |

### kb_nodes（知识库节点）

| 字段 | 类型 | 说明 |
|------|------|------|
| node_id | TEXT PK | dws wiki 节点 ID |
| space_id | TEXT | 知识库空间 |
| parent_id | TEXT | 父节点 |
| title | TEXT | |
| kind | TEXT | doc / sheet / file |
| synced_at | TEXT | 最近同步时间 |
| rag_doc_id | TEXT | RAGFlow 侧文档 ID |

## 四、里程碑与验收

| 阶段 | 内容 | 验收标准 |
|------|------|----------|
| M1 连通 | dws 授权导入并 `auth status` 通过 | `profile list` 显示目标组织；`event consume` 收到一条非 @ 群消息 |
| M2 存量 | 本机导出 JSON，跑归一化脚本入库 | `messages` 表条数与导出会话数吻合；附件可定位到文件 |
| M3 表格 | ETL 出 CSV/XLSX，写入 `dws aitable` | aitable 内出现消息量/活跃度图表 |
| M4 文件与知识库 | MinerU 解析附件；RAGFlow 建库；wiki 同步 | 对群里某份 PDF 提问，答出原文内容 |
| M5 工作台 | aitable 仪表盘或 H5 微应用上线 | 钉钉工作台内可打开，含检索与问答入口 |

## 五、需要的三样输入

1. **dws 认证包**：本机 `dws auth login && dws auth export --base64 > dws-auth.b64`，把 b64 发我。
2. **DashScope API Key**：千问问答与摘要用。
3. **历史导出运行机**：确认哪台 Windows/Mac 装 dingtalk-chat-exporter（或 im-mcp），导出样例 JSON 给我，用于写归一化适配器。

## 六、风险与退出条件

- dws 处于 Co-creation 阶段，部分事件投递未验证 → M1 不通过立即切兜底（CowAgent/LangBot）。
- 抓取类工具依赖钉钉客户端版本，客户端升级即可能失效 → 只做一次性补录，不做长期管道。
- 合规：抓取仅限本机本人账号、内部授权范围内，须有员工知情告知；本文件不构成合规意见。
