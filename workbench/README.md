# workbench

钉钉工作台 v1 的可运行骨架：采集器（dws → SQLite）+ 最小机器人（Stream + 千问）。

## 目录

```
db/schema.sql          四张表 + FTS5(trigram) 全文索引
collector/main.py      CLI：init-db / dump-raw / sync / stats / search
collector/dws_client.py dws 子进程封装
collector/normalize.py 原始事件 → canonical 记录（字段映射待实测修正）
collector/store.py     SQLite 读写
bot/bot.py             钉钉 Stream 机器人 + 千问回答
.env.example           全部需要的凭据
```

## 快速开始

```bash
cd workbench
python3 collector/main.py init-db

# 1) 先抓原始事件，确认字段名
python3 collector/main.py dump-raw --seconds 30

# 2) 对照 raw-events.ndjson 修正 collector/normalize.py 的 CANDIDATES

# 3) 正式采集（前台跑，生产用 systemd/supervisor 常驻）
python3 collector/main.py sync --seconds 600

# 4) 检索验证
python3 collector/main.py search --kw 预算下限
```

机器人：

```bash
pip install -r requirements.txt
cp .env.example .env      # 填 AppKey/AppSecret/DashScope Key
set -a && . ./.env && set +a
python3 bot/bot.py
```

## 已验证 / 未验证

| 项 | 状态 |
|---|---|
| SQLite 建表、FTS5 trigram 检索（中文 2 字与 4 字均命中） | 已验证 |
| 归一化去重（同消息重复插入被拒） | 已验证 |
| 非消息事件（已读等）被过滤 | 已验证 |
| dws 真实输出字段名 | **未验证**，需 `dump-raw` 后修正 |
| 机器人 Stream 收发 | **未验证**，需真实 AppKey |
| 千问调用 | **未验证**，需 DashScope Key |

## 已知限制

- `dws event consume` 是否覆盖全部群消息，取决于企业授权范围与 dws 版本，需实测
- 附件只记录 downloadCode，未实现按需下载与解析（MinerU 接入是下一步）
- 无消息切窗聚合，Dify 知识库灌入需另加聚合步骤
- SQLite 单机适合单用户；多人使用需先解决权限模型
