# VIS Demo – Agentic Visualization System 使用文档

## 1. 环境要求

| 依赖 | 版本 |
|---|---|
| Python | ≥ 3.11 |
| Node.js | ≥ 18 |
| npm | ≥ 9 |

---

## 2. 安装

### 2.1 Python 依赖

```bash
pip install -r requirements.txt
```

新增的关键包：
- `sse-starlette` — SSE 流式推送
- `aiofiles` — 异步文件 I/O
- `python-multipart` — 文件上传支持

### 2.2 前端依赖

```bash
cd frontend
npm install
```

---

## 3. 配置

在项目根目录的 `.env` 文件中设置（已存在，按需修改）：

```
OPENROUTER_API_KEY=sk-or-...
VLM_MODEL=qwen/qwen3-vl-235b-a22b-instruct
```

---

## 4. 启动

### 开发模式（推荐）

需要两个终端窗口：

**终端 1 — 后端**
```bash
cd /path/to/Agenticvisual
uvicorn web_server:app --host 0.0.0.0 --port 8000 --reload
```

**终端 2 — 前端**
```bash
cd /path/to/Agenticvisual/frontend
npm run dev
```

然后打开浏览器访问：**http://localhost:5173**

### 生产模式（单端口）

```bash
cd frontend
npm run build           # 构建前端到 frontend/dist/

cd ..
uvicorn web_server:app --host 0.0.0.0 --port 8000
```

访问：**http://localhost:8000**（后端直接托管前端静态文件）

---

## 5. 界面说明

### 三栏布局

```
┌─────────────────┬────────────────────────┬──────────────────────┐
│   左：数据面板   │     中：可视化画布      │    右：Agent 面板     │
└─────────────────┴────────────────────────┴──────────────────────┘
```

#### 左栏 — 数据面板

1. **CSV Upload 模式**
   - 拖拽或点击上传 CSV 文件
   - 系统自动识别列类型（Numeric / Categorical / Datetime）
   - 选择图表类型（scatter / bar / line / parallel / heatmap / sankey）
   - 配置编码字段（x / y / color / size 等），或点击 **Auto ✨** 一键填充
   - 设置画布宽高，点击 **▶ Generate View** 创建会话

2. **Paste Spec 模式**
   - 直接粘贴已有的 Vega 或 Vega-Lite JSON
   - 点击 **▶ Generate View** 创建会话

3. **Sessions**
   - 显示历史会话列表，点击可切换到已有会话（从 SQLite 恢复状态）

#### 中栏 — 可视化画布

- 使用 **vega-embed** 渲染交互式图表（支持 tooltip、缩放、选择等原生交互）
- 顶部工具栏：**{ } Spec** 按钮可切换查看/复制当前规范 JSON
- 底部 **Iteration Timeline**：Agent 每次更新视图都会在此追加一条记录；点击可回放该轮的图表状态

#### 右栏 — Agent 面板

**模式开关**
- **👥 Cooperative（协作式）**：Agent 每轮给出洞察与建议并等待用户输入
- **🤖 Autonomous（自主式）**：Agent 连续多轮探索，结束后返回总结报告

**三个 Tab**
- **💬 Chat**：主对话区，实时显示 Agent 的洞察、工具调用状态、分析结论
- **🔄 Iterations**：每轮迭代的折叠卡片，含关键洞察与推理过程
- **🔧 Tools**：工具调用日志，可展开查看输入/输出 JSON

**建议卡片（Next Steps）**
- 每次 run 完成后，Agent 自动生成 4-5 条可执行的下一步建议
- 点击任意建议卡片即可直接触发新一轮迭代，无需手动输入

**输入栏**
- `Enter`：发送消息
- `Shift+Enter`：换行
- **⏹ Stop**：中断当前正在执行的 Agent run

**功能按钮**
- **Reset**：将当前视图回退到会话建立时的 baseline spec
- **Export**：下载会话导出 zip 包

---

## 6. 导出包内容

点击 **Export** 下载的 zip 文件包含：

```
session_<id>.zip
├── session.json          # 会话元信息、对话历史、迭代记录
├── spec_history/
│   ├── current_spec.json # 当前最新 spec
│   ├── v1.json           # 历史版本 1
│   └── ...
└── report.md             # 自动生成的分析摘要（每轮洞察 + 推理 + 工具）
```

---

## 7. API 接口

后端 REST API（供调试或程序化调用）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 服务状态与模型可用性 |
| POST | `/api/files/upload` | 上传 CSV → `dataset_id` + 列信息 |
| POST | `/api/sessions` | 创建会话 |
| GET | `/api/sessions` | 会话列表 |
| GET | `/api/sessions/{id}` | 获取会话状态 |
| POST | `/api/sessions/{id}/query` | 提交 query（SSE 流式返回） |
| POST | `/api/sessions/{id}/reset` | 重置视图 |
| GET | `/api/sessions/{id}/export` | 下载 zip |
| DELETE | `/api/sessions/{id}` | 删除会话 |

完整 OpenAPI 文档：`http://localhost:8000/docs`

---

## 8. SSE 事件格式

`POST /api/sessions/{id}/query` 返回 `text/event-stream`，每行格式：

```
data: {"event": "<type>", "data": {...}}
```

| 事件类型 | 含义 |
|---|---|
| `iteration.started` | 某轮迭代开始 |
| `agent.message` | Agent 输出洞察与推理 |
| `tool.started` | 工具调用开始 |
| `tool.finished` | 工具调用结束（含结果） |
| `view.updated` | 产生新的 spec（含完整 JSON） |
| `iteration.finished` | 某轮迭代结束（含摘要） |
| `run.finished` | 整次 run 结束（含建议列表） |
| `error` | 错误 |
| `ping` | 保活心跳（可忽略） |

---

## 9. 数据持久化

系统使用 SQLite 存储会话与数据集元信息：
- 数据库文件：`vis_demo.db`（自动创建在项目根目录）
- 进程重启后会话状态可从 SQLite 恢复（切换到已有会话即可）
- 上传的 CSV 文件保存在 `uploads/` 目录

---

## 10. 注意事项

- Agent 处理过程中浏览器标签页不要关闭，SSE 连接断开会中断当前 run
- 每次 run 结束才会将会话状态持久化到 SQLite
- `main.py` 和 `system_api_server.py` 的功能不受影响，可继续独立使用
