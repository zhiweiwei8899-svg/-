
## 第一步：dws 自检（不泄露凭据）

如果你已有 dws 数据访问权限，先跑自检并把报告发给我：

```bash
python3 workbench/collector/selftest.py > dws-report.txt
```

报告只含：版本、认证组织名、子命令名、事件**字段名与类型**、字符串截断 12 字。
`token/secret/cookie/password` 一律替换为 `<redacted>`。
如仍敏感，加 `--no-names`，所有字符串只显示长度。
