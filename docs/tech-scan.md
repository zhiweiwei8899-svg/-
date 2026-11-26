# 技术扫描：千问 × 钉钉 数据底座选型（2026-11-20）

> 目标：打通千问与钉钉，围绕群消息读取、文件识别、知识库搭建、工作台搭建，
> 以群数据为底座。本文件记录 GitHub 全站扫描结论与每项结论的核实依据。
> 核实级别：【代码级】= 读过源码/文档原文；【文档级】= 核实过 README；
> 【未核实】= 仅有搜索结果，采用前需再验证。

## 一、硬约束（先于选型成立）

1. **群历史消息全量不存在传统意义的官方 API。**
   普通开放平台机器人只能收到 @自己 的消息。存量历史只能靠：
   消息搜索（经企业授权）、AI 听记导出、知识库/群文件导入。
   从启用时点起可持续积累。
2. **官方例外：`dws` 能以登录用户身份实时订阅全部群消息**（不止 @机器人），
   详见下文。这推翻了"只能 @机器人"的旧认知，但它走企业授权，
   且官方自述部分事件投递的 production readiness 未验证。
3. **灰色方案**（桌面客户端 hook、手机端转发如 SmsForwarder）
   能碰历史全量，但有封号与合规风险，本仓库选型不纳入生产路径。

## 二、核心发现：dws（官方 Workspace CLI）

- 仓库：https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli
  （4.1k★，Go，Apache-2.0，2026-11 活跃，【文档级】）
- 定位：钉钉官方开源的命令行工作台，"for humans and AI agents"。
- 与本需求逐项对照：

| 需求 | dws 能力 | 核实级别 |
|------|----------|----------|
| 群消息读取 | `dws event consume`：Stream WebSocket 订阅全部单聊/群消息等 33 类事件（消息、已读/撤回/表情、群生命周期、OA 审批、待办、听记）；`dws chat`：发/回复/搜索消息、群管理、撤回 | 【文档级】（README Key Services + Features 段） |
| 文件 | `dws drive`（列/搜/下载/上传）、`dws doc`（读写+媒体）、`dws minutes`（听记转写）、`dws sheet` | 【文档级】 |
| 知识库 | `dws wiki`：空间/成员/节点树/文档文件全操作 | 【文档级】 |
| 工作台 | `dws aitable`：AI 表格含图表与仪表盘；配套 `DingTalk-Real-AI/dingtalk-aicard`（互动卡片规范，29★） | 【文档级】 |
| 模型绑定 | 无绑定，任何 Agent 均可驱动（结构化 JSON + 内置 Agent Skills） | 【文档级】 |

- 前置条件：**企业管理员授权**（OAuth 设备流 + 最小权限 + 审计）。
  项目处于 Co-creation 阶段，上线前须在本企业实测事件投递。
- 同组织配套：`dingtalk-channel-sdk-python/go/java/nodejs`（机器人接入官方 SDK）、
  `dingtalk-openclaw-connector`（2.1k★，OpenClaw 官方钉钉插件）。

## 三、社区路线（dws 不可用或需要自托管时的替代）

### 全链路平台（机器人 + 模型 + 管理后台）

| 项目 | Stars | 钉钉接入 | 千问接入 | 核实级别 |
|------|-------|----------|----------|----------|
| zhayujie/CowAgent（原 chatgpt-on-wechat） | 48k | 官方 Stream 模式；源码 `channel/dingtalk/dingtalk_message.py` 处理 text/image/file/audio 四类消息，file 走 downloadCode 下载 | 模型表含 Qwen（qwen3.8-flash 等）一键切换 | 【代码级】 |
| langbot-app/LangBot | 19k | README 标 DingTalk=Official 频道 | `plugins/Runner/dashscope-agent`（DashScope 官方插件） | 【代码级】 |
| sangshy-go/AgentOne | 9（新） | README 含钉钉机器人 | DashScope/通义；知识库 RAG + 管理后台 | 【文档级】 |

### 知识库与文件识别组件

| 项目 | Stars | 角色 | 核实级别 |
|------|-------|------|----------|
| infiniflow/ragflow | 94k | RAG 引擎 + 深度文档理解（解析内置） | 【文档级】 |
| opendatalab/MinerU | 84k | PDF/Office/扫描件 → Markdown/JSON（OCR+表格公式），RAG 前处理 | 【文档级】 |
| zfanswer/dify-on-dingtalk | 247 | Dify ↔ 钉钉企业内部机器人（群聊/私聊） | 【文档级】 |
| chzealot/dingtalk-dify-connector | 46 | Dify Agent → 钉钉 AI 助理 | 【文档级】 |
| houyongsheng/dingtalk_card | 12 | Stream + 互动卡片形态的 Dify 接入 | 【文档级】 |
| breath57/dingtalk-skills | 102 | Agent 技能库：知识库/文档/AI 表格/群聊/日程，功能为 dws 子集（开源社区版） | 【文档级】 |
| ZoidbergPi/DingDocsScaper | 21 | 钉钉知识库文档批量导出（2024-07 后停更，仅作导入工具） | 【文档级】 |
| sunmh207/AI-Codereview-Gitlab | 1.9k | GitLab+LLM 代码评审 → 钉钉推送 + 可视化 Dashboard，含通义千问 | 【文档级】 |

## 四、推荐组合

```
千问(DashScope / Qwen Code) ──驱动── dws（官方授权）
   ├─ chat: 群消息实时流 + 搜索
   ├─ wiki: 知识库读写
   ├─ drive/doc: 文件获取
   └─ aitable: 工作台仪表盘
        ↓ 文件
MinerU 解析 → RAGFlow 向量库 → 千问问答
        ↘ 机器人回写群：dingtalk-channel-sdk，
          或 CowAgent/LangBot（自带网页管理后台）
```

选型次序：先试 `dws`（授权关能过则整体最省）；过不了授权关，
退 `CowAgent` 或 `LangBot` 自托管（Stream 机器人 + 后台现成），
文件识别与知识库固定用 MinerU + RAGFlow。

## 五、遗留决策点

- ~~企业管理员授权能否拿到~~ → **已确认可得（2026-11-20）**，dws 路线成立，决策见 ADR-0002。
- 工作台形态：aitable 仪表盘（钉钉内）vs 自建网页后台 → 待定。
- 落地时应按 ADR-0001 的失效条件新写一条选型 ADR，取代之。

---

## 六、钉钉聊天/群消息采集能力全景（2026-11-26 核实）

### 结论

该细分在全球 GitHub **没有高星项目**，天花板为 92★。原因：
① 官方不开放群历史全量接口；② 逆向本地加密库有法律与合规风险；
③ 钉钉客户端加密版本迭代频繁（V2→V3），维护成本高。
佐证：官方精选列表 `dingtalk-ai/awesome-dingtalk-integration`（216★）中
无任何采集类条目。

### 有采集能力的项目（全部）

| 项目 | ★ | 形态 | 能力（README 核实） | 活跃 |
|------|---|------|--------------------|------|
| stkoecn/im-mcp | 92 | 本机只读 MCP Server | 钉钉 7.x V2/V3 + 微信，群聊/单聊、图片/视频，MCP 协议暴露 | 2026-10 |
| abbr530/dingtalk-exporter | 34 | 离线解密导出 | 聊天记录 + 图片 + 附件 + 语音 → JSON | 2026-04 |
| idealistichacker/dingtalk-chat-exporter | 10 | 桌面端导出 | V2/V3 加密库、多账号、搜索、附件、离线 | 2026-11 |

易误认但非采集：`flydoos/DingTalkRevokeMsgPatcher`（806★，防撤回补丁）、
`mohuihui/DingTalk_Assistant`（251★，防撤回/多开）。

### 官方/半官方通道（可持续路线）

| 项目 | ★ | 可获取数据 | 限制 |
|------|---|-----------|------|
| DingTalk-Real-AI/dingtalk-workspace-cli (dws) | 4,185 | event consume 全部群/单聊消息 + chat 搜索 | 企业授权；Co-creation，未完全 GA |
| open-dingtalk/dingtalk-stream-sdk-python | 182 | 机器人收到的 @消息与文件（downloadCode） | 仅 @机器人 消息 |
| zhayujie/CowAgent / langbot-app/LangBot | 48k / 19k | 同上，可落库或进知识库 | 仅 @机器人 消息 |

### 选型结论

- 生产全量采集：**dws**（唯一官方全量通道）
- 历史存量一次性补录：**im-mcp**（只读设计最克制）或 chat-exporter
- 不做长期管道：采集类小项目随客户端升级即失效，作者维护不可依赖
- 合规：本地库解密属逆向客户端，条款大概率禁止；须内部授权与告知

证据级别：star 数与活跃度来自 GitHub API 实时查询（事实，会过期）；
能力描述来自 README（文档级）；未实测各项目在目标环境的可用性。
