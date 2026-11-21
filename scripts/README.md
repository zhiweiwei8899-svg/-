辅助脚本目录：构建、数据迁移、发布等一次性或自动化操作放这里，不放 `src/`。

## 现有脚本

- `ndjson_to_csv.py`：canonical NDJSON → CSV（UTF-8 BOM，Excel 直开）。
  用法见脚本头注释；数据契约见 docs/architecture.md。
