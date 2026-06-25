# 📋 Resume Matcher — AI 简历智能解析与岗位匹配系统

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)
[![Docker](https://img.shields.io/badge/Docker-✓-2496ED.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🎯 AI 驱动的简历解析与岗位匹配系统，帮助 HR 从海量简历中快速筛选匹配岗位要求的候选人。

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🔍 **智能简历解析** | 支持 PDF/DOCX/TXT/MD，三级提取（正则 → NER → LLM），中英文混合简历 |
| 🧠 **Multi-Agent 协作** | LangGraph 编排 4 个 AI Agent：解析 → 分析 → 匹配 → 解释 |
| 📊 **4 级渐进匹配** | 规则过滤 (10%) → TF-IDF (20%) → BGE 语义 (35%) → LLM 推理 (35%) |
| 🎯 **7 维度评分** | 学历 / 技能 / 经验 / 证书 / 语言能力 / 地点匹配 / 综合 |
| 💬 **可解释 AI** | LLM 逐条生成匹配理由，校招/社招差异化 ATS 优化建议 |
| 📈 **可视化仪表盘** | 雷达图 + 柱状图 + 饼图，直观展示匹配详情 |
| 🔌 **多 LLM 支持** | DeepSeek / OpenAI / 通义千问 / Ollama 自由切换 |
| 🇨🇳 **中文深度优化** | BGE 中文语义模型 + jieba 分词 + 140+ 技能分类体系 |
| 🐳 **一键部署** | Docker Compose 全栈，Vercel + Render 托管方案 |
| 🔒 **安全加固** | API Key 认证 + 密钥扫描 + 生产 SECRET_KEY 强校验 |

---

## 🏗️ 系统架构

```
┌──────────────┐    ┌──────────────────────────────────────┐    ┌──────────────┐
│   Next.js    │◄──►│          FastAPI Gateway              │◄──►│  PostgreSQL  │
│   Frontend   │    │  ┌──────────────────────────────┐    │    │   (pgvector) │
│ (Antd+ECharts)    │  │   LangGraph Agent Pipeline    │    │    │  ChromaDB    │
│               │    │  │  Parse → Match → Explain     │    │    │  Redis       │
│               │    │  └──────────────────────────────┘    │    │  MinIO (S3)  │
│               │    │  + Celery 异步任务 + API Key 认证    │    │              │
└──────────────┘    └──────────────────────────────────────┘    └──────────────┘
```

### 匹配流水线

```
简历上传 → NER提取 → LLM深度解析 → 结构化数据 ────┐
                                                    ↓
岗位输入 → JD解析 → 结构化需求 ─────────────────────┐
                                                    ↓
          ┌─────────────────────────────────────────┐
          │ Stage 1: 规则过滤     (学历/年限/GPA/证书) │ 10% / 20%
          │ Stage 2: TF-IDF + 模糊匹配   (关键词覆盖率) │ 20% / 35%
          │ Stage 3: BGE 语义相似度  (向量检索召回)    │ 35% / 45%
          │ Stage 4: LLM 深度推理   (7维分析+解释)    │ 35% / 0%
          └─────────────────────────────────────────┘
                               ↓
          综合得分 + 匹配理由 + 技能差距 + ATS 优化建议
```

---

## 🚀 快速开始

### 前置要求

- **Docker & Docker Compose** (推荐) 或 Python 3.11+ / Node.js 20+
- **LLM API Key** — [DeepSeek](https://platform.deepseek.com/) 免费注册即可

### Docker 一键启动

```bash
git clone <repo-url>
cd resume-matcher
cp .env.example .env
# 编辑 .env: 填入 LLM_API_KEY，其余保持默认即可
docker-compose up -d
```

自动启动 PostgreSQL 16 (pgvector) + ChromaDB + Redis + MinIO + Backend + Celery Worker + Frontend。

### 本地开发

```bash
# 1. 启动基础设施
docker-compose up -d postgres chromadb redis minio

# 2. 后端
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 3. Celery Worker (另一个终端，可选)
cd backend
celery -A app.tasks.celery_app worker --loglevel=info

# 4. 前端
cd frontend
npm install && npm run dev
```

访问：
| 服务 | 地址 |
|------|------|
| **前端界面** | http://localhost:3000 |
| **API 文档 (Swagger)** | http://localhost:8000/docs |
| **MinIO 控制台** | http://localhost:9001 (minioadmin/minioadmin) |

---

## 📖 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/resumes/upload` | 上传简历（PDF/DOCX/TXT/MD） |
| `GET` | `/api/v1/resumes/` | 简历列表（分页 + 状态筛选） |
| `GET` | `/api/v1/resumes/{id}` | 简历详情（含解析结果） |
| `GET` | `/api/v1/resumes/{id}/download` | 下载原始文件（从 MinIO 恢复） |
| `DELETE` | `/api/v1/resumes/{id}` | 删除简历 |
| `POST` | `/api/v1/jobs/` | 创建岗位（自动解析 + embedding） |
| `GET` | `/api/v1/jobs/` | 岗位列表 |
| `PATCH` | `/api/v1/jobs/{id}` | 更新岗位 |
| `PUT` | `/api/v1/jobs/{id}/toggle-active` | 切换启用状态 |
| `DELETE` | `/api/v1/jobs/{id}` | 删除岗位 |
| `POST` | `/api/v1/matching/analyze` | 🔥 单份简历匹配 |
| `POST` | `/api/v1/matching/analyze/stream` | 流式匹配（SSE） |
| `POST` | `/api/v1/matching/analyze/batch` | 批量匹配（异步，返回 task_id） |
| `GET` | `/api/v1/matching/results/{id}` | 查看匹配结果 |
| `GET` | `/api/v1/matching/results/` | 匹配历史列表 |
| `GET` | `/api/v1/reports/dashboard` | 仪表盘统计 |
| `GET` | `/api/v1/tasks/{task_id}` | 异步任务状态查询 |
| `GET` | `/api/v1/health` | 健康检查 |

---

## 🧪 示例

```bash
BASE=http://localhost:8000/api/v1

# 上传简历
curl -X POST $BASE/resumes/upload \
  -F "file=@data/sample_resumes/sample_resume_zh.txt"

# 创建岗位
curl -X POST $BASE/jobs/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"title":"AI研发工程师","raw_text":"...岗位描述..."}'

# 匹配分析（LLM 开启）
curl -X POST $BASE/matching/analyze \
  -H "Content-Type: application/json" \
  -d '{"resume_id":"xxx","job_id":"yyy","enable_llm":true}'

# 批量匹配（异步）
curl -X POST $BASE/matching/analyze/batch \
  -H "Content-Type: application/json" \
  -d '{"resume_ids":["a","b","c"],"job_id":"yyy","enable_llm":false}'
# → 返回 {"task_id":"...","status":"processing","total":3}
# → 轮询: curl $BASE/tasks/{task_id}
```

---

## 🛠️ 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **后端框架** | FastAPI (async) | 异步 REST API |
| **Agent 编排** | LangGraph | 4-Agent 状态图协作 |
| **NER** | spaCy + GLiNER (可配置) | 中英文实体识别 |
| **LLM** | DeepSeek / OpenAI / Qwen / Ollama | OpenAI-compatible 统一接口 |
| **嵌入模型** | BAAI/bge-large-zh-v1.5 | 中文语义向量 |
| **向量库** | ChromaDB | 简历/JD 相似度检索 |
| **数据库** | PostgreSQL 16 + pgvector | 结构化数据 + 向量 |
| **缓存/队列** | Redis | Celery 消息队列 |
| **对象存储** | MinIO (S3-compatible) | 生产环境文件存储 |
| **异步任务** | Celery | 简历解析 + 批量匹配 |
| **前端** | Next.js 14 + Ant Design 5 + ECharts 5 | 仪表盘 + 雷达图 |
| **部署** | Docker Compose / Vercel + Render | 全栈容器化 + 托管 |

---

## 📁 项目结构

```
resume-matcher/
├── backend/
│   ├── app/
│   │   ├── api/              # REST API（resumes/jobs/matching/reports/tasks）
│   │   ├── core/             # 配置、数据库、依赖注入、API Key 认证
│   │   ├── models/           # SQLAlchemy ORM（Resume/JobDescription/MatchResult）
│   │   ├── schemas/          # Pydantic 校验（7 维度评分等）
│   │   ├── services/
│   │   │   ├── parser/       # 文档加载 → NER → LLM → 分类 → 技能标准化
│   │   │   ├── matcher/      # 规则→TF-IDF→语义→LLM 4 级匹配
│   │   │   ├── agents/       # LangGraph 4-Agent 状态图
│   │   │   └── embedding/    # ChromaDB + BGE 编码服务
│   │   ├── tasks/            # Celery 异步任务（解析/批量匹配/清理）
│   │   └── utils/            # LLMClient、文件工具、MinIO 存储
│   ├── tests/                # 单元测试 + 集成测试（30+ 用例）
│   ├── alembic/              # 数据库迁移（含初始迁移）
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/              # 5 个页面（仪表盘/上传/岗位/匹配详情/报告）
│   │   ├── components/       # 7 个可复用组件
│   │   ├── lib/              # API 客户端 + TypeScript 类型
│   │   ├── stores/           # Zustand 状态管理
│   │   └── hooks/            # useApi 通用 hook
│   ├── vercel.json           # Vercel 部署配置
│   └── Dockerfile            # 多阶段构建（deps→builder→runner）
├── data/                     # 样本文件 + 技能分类体系（11 大类 140+ 技能）
├── docs/DEPLOYMENT.md        # 部署指南（Vercel/Render/Docker）
├── .github/workflows/ci.yml  # CI/CD 流水线（lint+test+coverage+build）
├── docker-compose.yml        # 开发环境
├── docker-compose.prod.yml   # 生产环境（资源限制 + 自动迁移 + 安全加固）
└── .env.example              # 环境变量模板（含详细注释）
```

---

## 🌍 部署

详细部署指南见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

| 方案 | 适用场景 | 复杂度 |
|------|---------|--------|
| **Docker Compose** | 单服务器全栈部署 | ⭐ |
| **Vercel + Render** | 前端 Vercel / 后端 Render / DB 托管 | ⭐⭐ |
| **Kubernetes** | 大规模弹性部署 | ⭐⭐⭐ |

`docker-compose.prod.yml` 提供生产级配置：资源限制、自动 alembic 迁移、非 root 运行、MinIO 文件存储。

---

## 🔒 安全

| 防护 | 实现 |
|------|------|
| **API Key 认证** | `X-API-Key` 请求头，`API_KEY` 为空时自动跳过（开发） |
| **密钥防泄露** | Git pre-commit hook 拦截 `.env`/`.pem`/`sk-*` 模式 |
| **Docker 防暴露** | `.dockerignore` 排除 `.env*`（仅保留 `.env.example`） |
| **生产强校验** | `config.py` 的 `@model_validator` 在 `DEBUG=false` 时强制覆盖 `SECRET_KEY` |
| **文件隔离** | 生产环境上传文件存储到 MinIO，本地临时文件自动清理 |

---

## 🤝 贡献

欢迎提交 Issue 和 PR！

## 📄 许可

MIT License
