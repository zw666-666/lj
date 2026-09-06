# 律镜 LawMirror

AI 驱动的智能类案检索与裁判规则分析平台。面向法律场景，把裁判文书进行结构化管理，支持自然语言检索、以案搜案、案例阅读、AI 问答、案例对标、法官画像与会员支付，构成从「文书入库 → 审核 → 检索 → 分析 → 付费」的完整业务闭环。

整体采用前后端分离架构：后端 **FastAPI + SQLAlchemy**，前端 **Vue 3 + TypeScript + Vite**。

## 核心功能

项目主要分为八个模块：

| 模块 | 说明 |
| --- | --- |
| 用户认证与权限 | 密码 bcrypt 哈希，JWT 签发短期 Access Token + 可轮换 Refresh Token，角色分为普通用户 / 会员 / 管理员 |
| 案例检索 | 支持自然语言、结构化筛选、以案搜案三种方式，Elasticsearch 优先、SQL + SQLite FTS5 降级，含法律同义词扩展与加权排序 |
| 案例阅读 | 展示详情与关联案例，记录阅读行为 |
| AI 问答 | 先检索相关案例再生成回答（RAG），通过 DeepSeek 流式接口（SSE）返回，减少大模型「胡编」 |
| 案例对标 | 选择 2–5 个案例或上传判决书文本，按法院层级、审判程序、案由、时间与裁判倾向构建对比矩阵 |
| 个人工作台 | 收藏、个人标签、笔记、分组、报告导出 |
| 管理后台 | 批量导入文书、查重、审核、下架/恢复/删除，案例状态按 `pending → summarizing → classifying → extracting → linking → completed` 流转 |
| 会员与支付 | 支付宝 Page Pay / 扫码支付，RSA2 签名 + 异步回调验签，会员订阅与用量控制 |

## 技术栈

- **后端**：FastAPI、SQLAlchemy、PyMySQL、Redis、Celery、Elasticsearch、RabbitMQ、python-jose（JWT）、passlib（bcrypt）、python-alipay-sdk、httpx
- **前端**：Vue 3、TypeScript、Vite、Pinia、Vue Router、Element Plus、Axios、ECharts、Three.js / OGL、qrcode
- **基础设施**：MySQL（生产 / 持久化）、SQLite（本地开发 + FTS5 全文检索）、Redis、RabbitMQ、Elasticsearch

## 项目结构

```
lj/
├── backend/
│   ├── app/
│   │   ├── api/          # 路由：auth、users、search、cases、profiles、compare、qa、workspace、admin、payment、alipay_payment
│   │   ├── core/         # 配置、数据库、安全、FTS5 全文检索、索引迁移、种子数据
│   │   ├── models/       # SQLAlchemy 模型
│   │   ├── schemas/      # Pydantic 模型
│   │   ├── services/     # 搜索、支付、短信、用量、案例加工流水线
│   │   ├── tasks/        # Celery 应用、流水线任务、定时任务
│   │   └── main.py       # FastAPI 应用入口
│   ├── Dockerfile
│   ├── init.sql          # 数据库初始化脚本
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/          # Axios 封装与拦截器
│   │   ├── components/   # 通用组件与布局
│   │   ├── router/       # 路由与守卫
│   │   ├── stores/       # Pinia 状态
│   │   └── views/        # 页面
│   ├── Dockerfile
│   ├── package.json
│   └── vite.config.ts
├── scripts/              # 运维脚本（ES 索引重构建、图片识别）
├── docker-compose.yml    # 服务编排
└── .env.example          # 环境变量示例
```

## 快速开始

### 方式一：Docker Compose（推荐）

1. 复制环境变量示例并修改：

   ```powershell
   Copy-Item .env.example .env
   ```

   至少把 `JWT_SECRET_KEY` 改成长随机字符串；使用 AI 问答还需填写 `DEEPSEEK_API_KEY`。

2. 启动全部服务：

   ```powershell
   docker compose up --build
   ```

3. 访问：

   - 前端：<http://localhost>
   - API 文档：<http://localhost:8000/docs>
   - 健康检查：<http://localhost:8000/api/health>
   - RabbitMQ 管理台：<http://localhost:15672>

   编排包含 MySQL、Redis、RabbitMQ、FastAPI、Celery Worker、Celery Beat 和前端 Nginx。

### 方式二：本地开发

后端（可先用 SQLite 降低本地启动成本）：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "sqlite:///./lvjing_dev.db"
uvicorn app.main:app --reload
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

## 环境变量

主要配置项见 `.env.example`，按模块分为 MySQL、Redis、RabbitMQ、JWT、DeepSeek AI、支付宝、短信验证码。后端通过 `pydantic-settings` 读取 `.env` 或 `../.env`，环境变量名与 `backend/app/core/config.py` 中的字段一一对应。

## 运维脚本

- `scripts/reindex_es.py`：把 MySQL 中的案例同步到 Elasticsearch，重建 `cases` 索引。
- `scripts/vision_describe.py`：调用豆包视觉模型描述图片（需设置 `VISION_API_KEY` 等环境变量）。

## 相关文档

- [项目技术实现讲解](./项目技术实现讲解.md)
- [律镜项目面试问答](./律镜项目面试问答.md)

## 安全说明

- 生产部署前务必修改 `.env.example` 中的所有默认值，尤其是 `JWT_SECRET_KEY` 与各数据库密码。
- 支付宝私钥、`DEEPSEEK_API_KEY`、短信密钥等敏感信息只写入本地 `.env`，不要提交到仓库。
- `.env`、`.env.production` 及数据库转储、密钥文件已在 `.gitignore` 中忽略。