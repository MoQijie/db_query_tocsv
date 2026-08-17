# 数据导出模块设计文档

> 本文档说明数据导出模块的设计思路、技术方案及代码改动。

---

## 一、需求背景

在原有智能数据库查询工具的基础上，新增**数据导出模块**，实现三大功能：

1. **多格式导出**：支持 CSV 和 JSON 两种文件格式
2. **自动化流程**：通过 Make 命令或 CLI 工具实现一键查询+导出
3. **AI 主动询问**：自然语言生成 SQL 后，AI 助手主动询问是否需要导出

---

## 二、总体架构

```
┌────────────────────────────────────────────────────────────────┐
│                       触发层（用户交互）                          │
│  ┌──────────────┐  ┌──────────────────────┐  ┌──────────────┐  │
│  │  Web UI      │  │  CLI 脚本             │  │  Make 命令   │  │
│  │  AI助手卡片   │  │  db_export_cli.py    │  │  export-sql  │  │
│  └──────┬───────┘  └──────────┬───────────┘  └──────┬───────┘  │
└─────────┼─────────────────────┼──────────────────────┼─────────┘
          │                     │                      │
          ▼                     ▼                      ▼
┌────────────────────────────────────────────────────────────────┐
│                      API 网关层 (FastAPI)                        │
│  ┌─────────────────────────┐  ┌────────────────────────────┐  │
│  │  POST /query-export     │  │  POST /query-export/natural│  │
│  │  (SQL → 执行 → 导出)     │  │  (NL→SQL→执行→导出，一键)   │  │
│  └────────────┬────────────┘  └─────────────┬──────────────┘  │
└───────────────┼─────────────────────────────┼──────────────────┘
                │                             │
                ▼                             ▼
┌────────────────────────────────────────────────────────────────┐
│                      服务层 (Services)                           │
│  ┌─────────────────────────┐  ┌────────────────────────────┐  │
│  │  query_wrapper          │  │  nl2sql_service            │  │
│  │  (执行 SQL，返回结果)     │  │  (将自然语言转换为 SQL)      │  │
│  └────────────┬────────────┘  └─────────────┬──────────────┘  │
└───────────────┼─────────────────────────────┼──────────────────┘
                │                             │
                ▼                             ▼
┌────────────────────────────────────────────────────────────────┐
│                      导出层 (export_service)                     │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  rows_to_csv()      — RFC 4180 标准 CSV，UTF-8 BOM      │  │
│  │  rows_to_json()     — 格式化 JSON，2 空格缩进            │  │
│  │  build_export_response() — 组装 bytes + Content-Type   │  │
│  └─────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
                │
                ▼
         ┌──────────────┐
         │ 二进制响应     │
         │ CSV / JSON   │
         └──────────────┘
```

---

## 三、详细设计

### 3.1 CSV 导出规范

遵循 RFC 4180 标准：

| 场景 | 处理方式 |
|------|----------|
| 字段含逗号 | 用双引号包裹 `"value,with,comma"` |
| 字段含双引号 | 内部引号转义为双引号 `"He said ""hello"""` |
| 字段含换行符 | 用双引号包裹并保留换行 |
| NULL / None 值 | 输出为空字符串 |
| Excel 兼容 | 添加 UTF-8 BOM（`\ufeff`），Excel 直接打开无乱码 |

### 3.2 JSON 导出规范

- 使用 2 空格缩进，便于阅读
- 保留 NULL 值为 JSON `null`
- 非字符串类型（日期、布尔等）使用 `default=str` 序列化
- 使用 `ensure_ascii=False` 保留非 ASCII 字符（如中文）

### 3.3 API 端点设计

#### `POST /api/v1/dbs/{name}/query-export`

执行 SQL 并直接返回文件下载。

**请求体：**
```json
{
  "sql": "SELECT * FROM users LIMIT 100",
  "format": "csv",
  "filename": "my_export"
}
```

**响应：** 二进制流，含 `Content-Disposition: attachment; filename="mydb_20240817_143052.csv"`

#### `POST /api/v1/dbs/{name}/query-export/natural`

自然语言 → AI 生成 SQL → 执行 → 导出，一气呵成。

**请求体：**
```json
{
  "prompt": "查询所有最近30天的活跃用户",
  "format": "json",
  "filename": "active_users"
}
```

### 3.4 CLI 工具设计

`db_export_cli.py` 提供命令行一键导出：

```bash
# 列出所有已注册的数据库
python scripts/db_export_cli.py --list-dbs

# SQL 查询导出为 CSV
python scripts/db_export_cli.py \
  --db mydb \
  --sql "SELECT * FROM orders WHERE amount > 100" \
  --format csv \
  --output results.csv

# 自然语言查询 + 导出
python scripts/db_export_cli.py \
  --db mydb \
  --prompt "查找所有未完成的任务" \
  --format json
```

### 3.5 AI 主动询问 UI 设计

在 Web 界面的自然语言查询场景中，SQL 生成成功后会在页面插入一个绿色的 AI 助手提示卡片：

```
┌─────────────────────────────────────────────────────────────┐
│ 🤖 AI 助手                                                    │
│                                                             │
│ 需要将这次查询结果导出为 CSV 或 JSON 文件吗？                  │
│                                                             │
│ AI 解释：[AI 生成的 SQL 说明]                                 │
│                                                             │
│  [ 导出 CSV ]   [ 导出 JSON ]                                │
└─────────────────────────────────────────────────────────────┘
```

- 仅在自然语言生成 SQL 成功后显示
- 执行导出时复用已生成的 SQL，无需重新执行 NL→SQL 步骤
- 绿色主题色（#16AA98）与系统主色调一致

---

## 四、代码改动清单

### 新增文件

| 文件路径 | 说明 |
|----------|------|
| `backend/app/services/export_service.py` | 导出服务：CSV/JSON 生成逻辑 |
| `backend/scripts/db_export_cli.py` | CLI 一键导出工具 |

### 修改文件

| 文件路径 | 改动说明 |
|----------|----------|
| `backend/app/models/schemas.py` | 新增 `ExportQueryInput`、`ExportNLQueryInput` schema |
| `backend/app/api/v1/queries.py` | 新增 `/query-export` 和 `/query-export/natural` 两个端点 |
| `backend/pyproject.toml` | 添加 `requests>=2.32.0` 依赖（CLI 工具使用） |
| `frontend/src/pages/Home.tsx` | 新增 AI 助手导出提示卡片及导出功能 |
| `Makefile` | 新增 `export-sql`、`export-nl`、`export-list` 自动化命令 |

---

## 五、关键设计决策

### 5.1 为什么用 FastAPI `Response` 而非 `FileResponse`？

CSV/JSON 内容由 `build_export_response()` 动态生成，文件名含时间戳（避免覆盖），且有自定义 MIME 类型需求，因此使用底层 `Response` 对象手动设置 `Content-Disposition` 头，灵活度更高。

### 5.2 为什么复用 `_run_export` 辅助函数？

两个导出端点共享相同的查询执行 → 导出流程，仅在 SQL 来源上有区别（手动 SQL vs. AI 生成 SQL）。抽取 `_run_export()` 避免重复代码。

### 5.3 为什么 CLI 和 API 并存？

CLI 工具面向**自动化脚本**和**运维场景**，可以在服务器上通过 Make 命令或 cron 定时任务触发，不需要浏览器或 Web 界面。两种方式共存，互为补充。

### 5.4 UTF-8 BOM 的作用

Excel 在默认情况下以 ANSI 编码打开 CSV，如果文件是 UTF-8 编码且不含 BOM，中文字符会显示为乱码。添加 `\ufeff` BOM 头（0xEF 0xBB 0xBF）可让 Excel 自动识别为 UTF-8 编码。

---

## 六、扩展性设计

### 新增导出格式

在 `export_service.py` 中新增一个函数，在 `build_export_response()` 中增加分支即可：

```python
def rows_to_excel(columns, rows):
    # TODO: 实现 xlsx 格式
    pass
```

### 新增 API 端点

在 `queries.py` 中注册新路由即可，复用 `_run_export()` 辅助函数。

### 存储到云存储

修改 API 端点，先上传到 S3/OSS/GCS，返回下载链接而非直接返回文件流，适合大文件场景。

---

## 七、安全性说明

- SQL 验证：所有 SQL 均经过 `sql_validator.py` 验证，仅允许 SELECT 语句
- 自动 LIMIT：未带 LIMIT 的查询自动注入 `LIMIT 1000`，防止全表导出内存溢出
- 大量数据警告：前端对超过 10,000 行的结果弹出确认框
- CORS 配置：由后端 `.env` 中 `CORS_ORIGINS` 控制，默认 `*`