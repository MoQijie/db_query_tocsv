# 数据导出模块运行指南

> 本文档说明如何启动服务、运行导出功能，以及所需的环境依赖。

---

## 一、环境要求

### 基础环境

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | >= 3.12 | 后端运行时 |
| Node.js | >= 18 | 前端构建 |
| npm | >= 9 | 前端依赖安装 |
| UV | 最新版 | Python 包管理工具（项目推荐） |

### 数据库（目标数据库）

| 数据库 | 支持类型 | 连接方式 |
|--------|----------|----------|
| PostgreSQL | 9.x ~ 16.x | `postgresql://user:pass@host:port/db` |
| MySQL | 5.7 / 8.x | `mysql://user:pass@host:port/db` |

> 目标数据库即需要查询和导出数据的业务数据库，不需要额外部署。

### API 密钥

| 密钥 | 必需 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` | 仅 NL 功能必需 | 用于自然语言→SQL 转换，不使用 NL 功能时可跳过 |

---

## 二、环境安装

### 2.1 安装 Python 依赖（使用 UV）

```bash
cd /home/coder/project/homework/db_query_project/w2/db_query

# 安装后端依赖（包括开发依赖）
make install-backend

# 或手动执行
cd backend && uv sync --extra dev
```

### 2.2 安装前端依赖

```bash
make install-frontend

# 或手动执行
cd frontend && npm install
```

### 2.3 配置环境变量

```bash
cd /home/coder/project/homework/db_query_project/w2/db_query/backend

# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填入以下配置
```

**.env 文件配置项：**

```bash
# 必需：OpenAI API 密钥（仅自然语言查询功能需要）
OPENAI_API_KEY=sk-your-openai-key-here

# 可选：SQLite 数据库存储路径（默认 ~/.db_query/db_query.db）
DB_QUERY_DATA_DIR=~/.db_query

# 可选：日志级别
LOG_LEVEL=INFO

# 可选：CORS 允许的源（默认 * 允许所有）
CORS_ORIGINS=*

# 可选：查询默认 LIMIT 行数
QUERY_DEFAULT_LIMIT=1000

# 可选：历史记录保留条数
QUERY_HISTORY_RETENTION=50
```

---

## 三、启动服务

### 方式一：一键启动（后端 + 前端并行）

```bash
cd /home/coder/project/homework/db_query_project/w2/db_query
make dev
```

输出：
```
Starting backend server on http://localhost:8000
Starting frontend server on http://localhost:5173
```

### 方式二：分别启动

```bash
# 终端 1：后端
make dev-backend

# 终端 2：前端
make dev-frontend
```

### 验证服务状态

```bash
make health
```

输出示例：
```json
{"status":"ok","version":"0.1.0"}
```

---

## 四、使用方法

### 4.1 Web 界面操作

1. 打开浏览器访问 **http://localhost:5173**
2. 在左侧边栏添加目标数据库连接（PostgreSQL 或 MySQL URL）
3. 在中部元数据面板查看表结构
4. **手动 SQL 导出：**
   - 在"MANUAL SQL"标签输入 SQL，点击"EXECUTE"
   - 查询完成后，点击结果区域右上角的"EXPORT CSV"或"EXPORT JSON"
5. **自然语言 + AI 导出：**
   - 切换到"NATURAL LANGUAGE"标签
   - 输入自然语言描述（如"查询所有活跃用户"）
   - 点击"GENERATE SQL"，AI 生成 SQL 后，页面自动弹出绿色导出提示卡
   - 点击"导出 CSV"或"导出 JSON"，浏览器自动下载文件

### 4.2 Make 命令导出

> 不需要启动 Web 界面，适合服务器端自动化操作

```bash
cd /home/coder/project/homework/db_query_project/w2/db_query
```

**查看可用数据库：**
```bash
make export-list
```

**SQL 查询导出为 CSV：**
```bash
make export-sql DB=mydb SQL="SELECT * FROM users LIMIT 100" FORMAT=csv
```

**SQL 查询导出为 JSON（指定输出文件）：**
```bash
make export-sql DB=mydb SQL="SELECT * FROM orders" FORMAT=json OUTPUT=my_orders.json
```

**自然语言查询导出（AI 生成 SQL）：**
```bash
# 中文
make export-nl DB=mydb PROMPT="查询所有最近30天的活跃用户" FORMAT=csv

# 英文
make export-nl DB=mydb PROMPT="Show all orders with amount over 1000" FORMAT=json
```

> 注意：`make export-nl` 需要配置 `OPENAI_API_KEY`

### 4.3 CLI 脚本直接运行

```bash
cd /home/coder/project/homework/db_query_project/w2/db_query/backend

# 列出数据库
uv run python scripts/db_export_cli.py --list-dbs

# SQL 导出
uv run python scripts/db_export_cli.py \
  --db mydb \
  --sql "SELECT id, name, email FROM users WHERE active = true" \
  --format csv \
  --output active_users.csv

# 自然语言导出
uv run python scripts/db_export_cli.py \
  --db mydb \
  --prompt "查找所有未完成的任务" \
  --format json

# 指定 API 地址（默认 http://localhost:8000）
uv run python scripts/db_export_cli.py \
  --db mydb \
  --sql "SELECT * FROM products" \
  --format csv \
  --base-url http://your-server:8000
```

---

## 五、API 直接调用

使用 curl 或其他 HTTP 客户端：

```bash
# SQL 查询 + CSV 导出
curl -X POST "http://localhost:8000/api/v1/dbs/mydb/query-export" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM users LIMIT 100", "format": "csv"}' \
  --output export.csv

# 自然语言查询 + JSON 导出
curl -X POST "http://localhost:8000/api/v1/dbs/mydb/query-export/natural" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "查询所有活跃用户", "format": "json"}' \
  --output export.json

# 导出时自定义文件名（不带扩展名）
curl -X POST "http://localhost:8000/api/v1/dbs/mydb/query-export" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM orders", "format": "csv", "filename": "monthly_orders"}' \
  --output monthly_orders.csv
```

---

## 六、Makefile 命令汇总

| 命令 | 说明 |
|------|------|
| `make dev` | 启动后端 + 前端开发服务器 |
| `make dev-backend` | 仅启动后端（http://localhost:8000） |
| `make dev-frontend` | 仅启动前端（http://localhost:5173） |
| `make export-sql DB=name SQL="..."` | SQL 查询导出（FORMAT=csv\|json） |
| `make export-nl DB=name PROMPT="..."` | NL→SQL→导出（FORMAT=csv\|json） |
| `make export-list` | 列出所有已注册的数据库 |
| `make health` | 检查后端服务状态 |
| `make install` | 安装所有依赖（后端 + 前端） |
| `make check` | 运行代码检查（lint + test） |

---

## 七、常见问题

### Q：make export-nl 报 "OPENAI_API_KEY not configured"

**解决：** 在 `backend/.env` 文件中添加 `OPENAI_API_KEY=sk-your-key`，然后重启后端服务。

### Q：导出的 CSV 用 Excel 打开乱码

**原因：** Excel 默认不以 UTF-8 编码打开 CSV。
**解决：** 代码已自动添加 UTF-8 BOM 头。如仍乱码，可先在 Excel 中选择"数据→从文本文件"导入。

### Q：导出的行数少于预期

**原因：** 系统默认 LIMIT 1000 行，防止内存溢出。
**解决：** 在 SQL 中显式指定更大的 LIMIT 值，如 `SELECT * FROM orders LIMIT 100000`。

### Q：提示 "Metadata not found"

**原因：** NL→SQL 功能需要数据库元数据（表结构信息）作为上下文。
**解决：** 在 Web 界面中打开目标数据库，系统会自动加载元数据。也可以启动后端后，在界面上刷新一次数据库。

### Q：前端修改后页面没更新

**解决：** 确保前端开发服务器在运行（`make dev-frontend`），修改 `.tsx` 文件后 Vite 会热更新，刷新浏览器即可。