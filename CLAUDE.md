# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 项目概述

**Resume Matcher** — AI 驱动的简历解析与岗位匹配系统，帮助 HR 从海量简历中快速筛选匹配岗位要求的候选人。

- **简历解析**: PDF/DOCX/TXT → NER + LLM 三级策略 → 结构化数据
- **匹配流水线**: 规则过滤 → TF-IDF → BGE 语义 → LLM 深度推理（4 级渐进）
- **Agent 编排**: LangGraph 状态图，4-Agent 协同（parse → analyze → match → explain）
- **技术栈**: FastAPI (async) + LangGraph + spaCy/GLiNER + ChromaDB + PostgreSQL 16 (pgvector) + Redis/Celery + MinIO + Next.js 14 + Ant Design + ECharts

---

## 常用命令

### 后端

```bash
cd backend

# 安装依赖（含 dev）
pip install -e ".[dev]"
python -m spacy download zh_core_web_sm

# 启动开发服务器
uvicorn app.main:app --reload --port 8000

# 运行所有测试
pytest

# 运行单个测试
pytest tests/test_parser.py::TestNERExtractor::test_extract_email -v

# 覆盖率
pytest --cov=app --cov-report=html

# Lint & 格式化
ruff check .
ruff format .

# 类型检查
mypy app/

# 数据库迁移
alembic revision --autogenerate -m "描述"
alembic upgrade head

# Celery Worker
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
```

### 前端

```bash
cd frontend

npm install
npm run dev        # 开发服务器 http://localhost:3000
npm run build      # 生产构建
npm run lint       # ESLint
```

### Docker

```bash
# 启动基础设施（本地开发时只启动服务，不启动 backend/frontend 容器）
docker-compose up -d postgres chromadb redis minio

# 全栈一键启动
docker-compose up -d

# 查看日志
docker-compose logs -f backend

# 数据库迁移（Docker 环境）
docker-compose exec backend alembic upgrade head
```

---

## 架构关键点

### 匹配流水线权重

匹配 API 根据是否启用 LLM 使用不同的权重聚合：

| Stage | 启用 LLM | 未启用 LLM |
|-------|----------|------------|
| Rule | 0.10 | 0.20 |
| TF-IDF | 0.20 | 0.35 |
| Semantic (BGE) | 0.35 | 0.45 |
| LLM | 0.35 | — |

`enable_llm` 参数控制 Stage 4。批量匹配（`/analyze/batch`）默认 `enable_llm=false` 以节约成本。

### MatchingState — Agent 管线的核心契约

[backend/app/services/agents/graph.py](backend/app/services/agents/graph.py) 中的 `MatchingState` TypedDict 是所有 Agent 共享的状态。修改 Agent 行为时必须理解这个结构：

- 输入: `resume_text`, `jd_text`, `enable_llm` (bool, 控制 Stage 4)
- 中间结果: `resume_parsed` (ParsedResumeData), `jd_parsed` (ParsedJDData), `rule_result`, `tfidf_result`, `semantic_result`, `llm_result`
- 最终输出: `overall_score`, `dimension_scores`, `matched_skills`, `missing_skills`, `reasoning`, `suggestions`, `is_hard_pass`
- 流控: `error` (非空时触发错误处理)

API 路由通过 `matching_graph.ainvoke(state)` 调用 Agent 管线。当 state 中已存在 `resume_parsed` 和 `jd_parsed` 时，`parse_all` 节点自动跳过（避免重复解析）。

### LLM 调用入口

所有 LLM 调用统一通过 [backend/app/utils/llm_client.py](backend/app/utils/llm_client.py) 的 `LLMClient` 类。它封装了一个 `AsyncOpenAI` 客户端——任何 OpenAI-compatible API 都可直接使用。关键方法：

- `chat()` — 普通文本补全
- `chat_with_json_output()` — 给定 Pydantic schema，返回解析后的 dict
- `chat_stream()` — SSE 流式输出

切换 LLM Provider 只需修改 `.env` 中的 `LLM_PROVIDER`、`LLM_MODEL`、`LLM_BASE_URL`、`LLM_API_KEY`，无需改代码。

### 数据库

- PostgreSQL 16 + **pgvector** 扩展（docker-compose 使用 `pgvector/pgvector:pg16` 镜像）
- SQLAlchemy 2.0 async + asyncpg
- 所有表使用 UUID 主键
- **开发**: `Base.metadata.create_all` 在 FastAPI `lifespan` 中自动建表（仅 `DEBUG=true` 时生效）
- **生产**: 必须使用 alembic 迁移。`docker-compose.prod.yml` 中 backend 启动时自动执行 `alembic upgrade head`
- 初始迁移位于 `alembic/versions/20240624_0001_initial_schema.py`
- `get_db` 依赖注入：成功自动 commit，异常自动 rollback

### 文件存储

- **开发**: 文件存储在本地 `data/uploads/` 目录
- **生产**: 解析完成后上传到 MinIO，本地临时文件自动清理。`file_path` 字段存储 MinIO object name（如 `resumes/{uuid}.pdf`）
- MinIO 配置通过 `MINIO_*` 环境变量控制。[storage.py](backend/app/utils/storage.py) 提供 `MinIOStorage` 封装
- 文件下载端点 `GET /api/v1/resumes/{id}/download` 支持从 MinIO 恢复文件

### Celery 异步任务

三个任务位于 [matching_tasks.py](backend/app/tasks/matching_tasks.py)：
- `parse_resume_async` — 生产模式下上传简历后异步解析（dev 模式同步解析）
- `batch_match_async` — 批量匹配（含进度上报）
- `cleanup_old_files` — 清理 N 天前的失败记录和临时文件

任务状态通过 `GET /api/v1/tasks/{task_id}` 查询。`POST /api/v1/matching/analyze/batch` 返回 `task_id` 供前端轮询。

### 简历解析三级策略

1. **正则** ([ner_extractor.py](backend/app/services/parser/ner_extractor.py)): 毫秒级提取邮箱/电话/URL
2. **GLiNER + spaCy**: 零样本实体识别 + 技能词汇匹配。GLiNER 默认关闭（`ENABLE_GLINER=false`），LLM 已覆盖同类实体，生产环境建议保持关闭
3. **LLM** ([llm_extractor.py](backend/app/services/parser/llm_extractor.py)): 深度语义理解复杂字段

NER 和 LLM 结果会合并——NER 提取的高置信度字段（email/phone）优先覆盖 LLM 结果，技能做并集去重。

### 向量存储与相似度检索

- [vector_store.py](backend/app/services/embedding/vector_store.py) — ChromaDB 封装，upsert/query/delete
- [embedding_service.py](backend/app/services/embedding/embedding_service.py) — BGE 编码 + ChromaDB 存储桥接
- 上传简历时自动创建 embedding，删除时自动清理
- 创建 JD 时自动创建 embedding
- `find_similar_resumes(jd_id, top_k=10)` 用于按岗位向量召回候选简历

### 认证

- [security.py](backend/app/core/security.py) 提供 `require_api_key` FastAPI 依赖
- 检查 `X-API-Key` 请求头
- `API_KEY` 为空时自动跳过（开发模式），非空时强制校验
- 当前未强制所有路由，可按需添加到 Admin/管理类接口

### 前端状态管理

使用 **Zustand** 进行状态管理（主题切换 + 侧边栏），**echarts-for-react** 封装 ECharts 图表（柱状图/饼图/雷达图）。共 7 个可复用组件（StatCard, ScoreTag, ChartCard, EmptyState, ErrorState, ConfirmButton, PageHeader）。`useApi` 通用 hook 封装了 axios 请求和 loading/error 状态。

---

## 环境配置注意事项

### 本地开发 vs Docker

`.env.example` 中的 host 配置面向 Docker Compose（服务名如 `postgres`、`chromadb`、`redis`），本地开发时需要改为 `localhost`：

```bash
# 本地开发时覆盖（config.py 的默认值已是 localhost，可不设）
POSTGRES_HOST=localhost
CHROMA_HOST=localhost
REDIS_URL=redis://localhost:6379/0
MINIO_ENDPOINT=localhost:9000
```

### 前端环境变量

前端需要知道后端 API 地址。在 `frontend/` 目录创建 `.env.local`：

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

---

## 项目结构

```
resume-matcher/
├── backend/
│   ├── app/
│   │   ├── api/              # REST API 路由
│   │   │   ├── resumes.py    # 简历上传/管理（MinIO 存储 + Celery 异步）
│   │   │   ├── jobs.py       # JD 管理（含 embedding）
│   │   │   ├── matching.py   # 匹配分析（调 Agent 管线 graph.ainvoke）
│   │   │   ├── reports.py    # 报告/仪表盘
│   │   │   └── tasks.py      # Celery 任务状态查询
│   │   ├── core/             # 配置(Settings)、DB、依赖注入、API Key 认证
│   │   ├── models/           # SQLAlchemy ORM (Resume, JobDescription, MatchResult)
│   │   ├── schemas/          # Pydantic 校验 (ParsedResumeData, DimensionScores 等)
│   │   ├── services/
│   │   │   ├── parser/       # 简历解析引擎 (加载→NER→LLM→标准化)
│   │   │   ├── matcher/      # 4 级匹配流水线 (rule→tfidf→semantic→llm)
│   │   │   ├── agents/       # LangGraph Agent (API 入口已统一走 graph.ainvoke)
│   │   │   └── embedding/    # vector_store + embedding_service
│   │   ├── tasks/            # Celery 异步任务（解析/批量匹配/清理）
│   │   └── utils/            # LLMClient, file_utils, storage(MinIO)
│   ├── tests/                # 测试（parser + rule/tfidf/weighting/classifier/llm_client/api）
│   ├── alembic/              # 数据库迁移（含初始迁移 0001）
│   ├── pyproject.toml        # 项目配置 + ruff/pytest 设置
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/              # Next.js App Router 页面（5 个页面）
│   │   ├── components/       # 可复用组件（StatCard, ScoreTag, ChartCard 等 7 个）
│   │   ├── lib/              # api.ts (Axios), types.ts (TS 类型)
│   │   ├── stores/           # Zustand 状态管理
│   │   └── hooks/            # useApi 通用 hook
│   └── package.json
├── data/                     # 样本简历/JD + skill_taxonomy.json (11 大类 140+ 技能)
├── docker-compose.yml        # 开发环境（bind mount + hot-reload）
├── docker-compose.prod.yml   # 生产环境（资源限制 + 自动迁移 + 安全加固）
├── docs/DEPLOYMENT.md        # 部署指南（Vercel + Render + Docker）
└── .env.example
```

---

## 添加新功能的指南

### 添加新的匹配维度

1. `app/services/matcher/llm_matcher.py` — LLM prompt 中添加分析维度
2. `app/schemas/matching.py` — `DimensionScores` 添加新字段
3. `app/services/agents/match_agent.py` — 聚合逻辑加入新维度
4. `frontend/src/lib/types.ts` — 同步 TS 类型
5. 前端匹配详情页雷达图添加新的 indicator

### 添加新的简历文件格式

在 `app/services/parser/document_loader.py` 中添加 `_load_xxx()` 静态方法，在 `load()` 的 `loaders` 字典中注册扩展名。

### 添加新的 NER 实体类型

1. `app/services/parser/ner_extractor.py` 的 `extract()` 中添加提取逻辑
2. `app/schemas/resume.py` 的 `ParsedResumeData` 添加字段
3. ORM 使用 JSONB，Schema 变更后数据库自动适配

---

## 关键设计决策

### 为什么用多级匹配而非直接 LLM？

1. **成本**: LLM 调用贵，大批量时先用规则+向量过滤
2. **稳定性**: LLM 有随机性，向量匹配结果可复现
3. **效率**: 规则/向量毫秒级，LLM 秒级
4. **可解释性**: 每阶段独立结果，便于调试

### 为什么用 LangGraph 而非 LangChain？

LangGraph 状态图模型更适合多 Agent 协作——每个 Agent 是独立节点，通过 `MatchingState` 共享状态，天然支持条件分支和错误处理。

---

## 项目亮点

1. **Multi-Agent 架构**: LangGraph 编排 4 个 AI Agent 协同完成简历解析→JD分析→智能匹配→可解释报告
2. **多级渐进匹配**: 规则过滤→TF-IDF→BGE 语义→LLM 深度推理，兼顾效率与精度（7 维度评分）
3. **可解释 AI**: LLM 逐条生成匹配理由 + ATS 优化建议（校招/社招差异化）
4. **生产级工程**: FastAPI 异步 + Docker 容器化 + MinIO 对象存储 + Celery 异步任务 + CI/CD
5. **向量检索**: BGE 中文语义模型 + ChromaDB 相似度召回，匹配前预筛选候选简历
6. **安全防护**: API Key 认证 + pre-commit 密钥扫描 + .dockerignore 防泄露 + 生产 SECRET_KEY 强校验
