# SmartSupport Agent

面向 3C 数码与智能家电电商售后的企业级 Multi-Agent 求职项目。系统包含顾客商城和员工客服后台，将真实下单流程、DeepSeek、LangGraph、中文混合检索、人工工单、申诉调查、权限治理和用户提问分析组合为完整业务闭环。

## 功能

- DeepSeek `deepseek-chat` 真实流式生成，失败时自动降级
- Support Orchestrator + 四个边界清晰的业务 Agent，统一结构化输出和工具白名单
- LangGraph 条件路由、持久化检查点和多轮订单上下文
- 顾客专属商城：8 个本地图片商品、搜索筛选、持久化购物车和收货地址
- 模拟交易闭环：结算、模拟支付、库存扣减、订单详情和物流进度
- 订单专属客服：自动携带订单上下文，咨询记录与订单、用户和会话关联
- 商城消息每 3 秒同步到员工会话队列，可查看用户问题、Agent 回答、路由和证据
- 售后申诉中心：申诉、订单、工单、证据和 7 个 Agent 节点统一展示
- 复杂申诉并行执行订单、政策、技术、财税调查，经过方案生成、Risk Agent 和人工审批
- `BAAI/bge-small-zh-v1.5` 中文向量 + 关键词混合检索
- PostgreSQL 16 + pgvector 统一支撑本地、测试和生产数据
- PDF、Word、Markdown、TXT 上传、解析、分段、启停与删除
- 订单、物流、退款工具，用户确认、高金额审批和越权拦截
- 转人工自动建单，客服接单、回复、解决完整闭环
- JWT、bcrypt、顾客与全权限客服账号隔离
- 会话消息、模型调用、审计日志和 LangGraph 状态持久化
- 真实用户提问排行、知识覆盖率与按商品隔离的语义知识缺口聚类
- 3200 条合成用户问题生成器和 1000 条离线批量测试报告
- Redis 多实例限流，内存限流降级
- Prometheus 全链路指标与告警规则、自动加载的 Grafana Agent 总览看板
- 25 篇结构化知识文档、93 个混合检索分段
- PostgreSQL/pgvector 后端测试、前端生产构建和 GitHub Actions

质量看板直接分析已持久化的真实会话，展示高频问题，并根据回答引用识别知识库缺口。未覆盖问题使用 BGE `vector(512)` 在相同商品内做余弦相似度聚类，例如“P-C3 支持防水吗？”和“这个耳机碰到水会坏吗？”会合并为同一个问题簇，同时保留每条原始问法和来源。

## 快速启动

需要 Python 3.11+、Node.js 20+ 和 PostgreSQL 16 + pgvector。推荐先启动基础设施：

```powershell
docker compose up -d db redis
```

当前电脑使用 Conda 环境 `Deep-Learning`。

后端：

```powershell
conda activate Deep-Learning
cd server
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

前端：

```powershell
cd web
npm install

# 员工客服后台
npm run dev:employee

# 另开一个终端启动顾客商城
npm run dev:mall
```

- 员工客服后台：`http://127.0.0.1:5173`
- 顾客商城：`http://127.0.0.1:5175`
- OpenAPI：`http://127.0.0.1:8000/docs`
- Prometheus：`http://127.0.0.1:8000/metrics`
- 就绪检查：`http://127.0.0.1:8000/health/ready`

首次启动会下载约 100 MB 的中文 Embedding 模型，之后从本机缓存加载。

## 演示账户

| 角色 | 用户名 | 密码 | 能力 |
|---|---|---|---|
| 全权限客服 | `admin` | `Admin123!` | 会话、工单、申诉受理与审批、知识库、质量分析 |
| 顾客 | `customer` | `Customer123!` | 商城、购物车、下单、订单客服、售后申诉 |

这些账号只用于本地演示，生产部署必须更换密码和 `AUTH_SECRET`。

## 演示流程

| 场景 | 操作 |
|---|---|
| 商城下单 | 顾客登录，商品加入购物车，选择默认地址并完成模拟支付 |
| 订单客服 | 在订单详情点击“咨询客服”，询问“这个订单到哪里了？” |
| 售后申诉 | 在订单详情提交申诉，再用全权限客服账号完成受理、调查和审批 |
| DeepSeek + 引用 | `七天无理由有什么要求？` |
| 多轮记忆 | 先输入 `查询订单 XY20260702`，再输入 `它到哪里了？` |
| 低风险退款 | `我想退款 XY20260701`，再输入 `确认退款 XY20260701` |
| 高风险审批 | `我想退款 XY20260702` |
| 多 Agent 申诉 | `耳机维修两次仍然坏了，我要维权` |
| Risk Agent | `账号收到异地登录提醒` |
| 越权拦截 | `查询订单 XY20260703` |
| 人工闭环 | 输入 `我要人工客服`，进入工单中心接单、回复并解决 |
| 文档管理 | 上传文档，查看分段，禁用后再次检索 |
| 提问分析 | 进入质量看板，查看高频问题和知识库未覆盖问题 |

演示订单 `XY20260701` 和 `XY20260702` 属于管理员演示用户，`XY20260703` 用于越权测试。

## Docker 生产拓扑

```powershell
docker compose up --build
```

Compose 包含两个独立的 React/Nginx 站点（员工后台 `5173`、顾客商城 `5175`）、FastAPI、PostgreSQL/pgvector、Redis、Prometheus 和 Grafana。PostgreSQL 默认同时暴露到本机 `5432`，供本地后端和真实数据库测试使用。

监控服务随 Compose 自动配置，无需在 Grafana 中手工添加数据源或导入 Dashboard：

- Prometheus：`http://127.0.0.1:9090`
- Grafana：`http://127.0.0.1:3000`
- Dashboard：`SmartSupport / SmartSupport Agent Overview`
- Grafana 账号：读取 `.env` 中的 `GRAFANA_ADMIN_USER` 和 `GRAFANA_ADMIN_PASSWORD`

监控覆盖 HTTP 请求与延迟、Agent 路由与人工升级、DeepSeek 调用与 Token、RAG 命中率、业务工具执行以及进程资源。Prometheus 已加载服务不可用、HTTP 错误和延迟、模型错误、RAG 未命中和工具失败规则；当前不包含 Alertmanager 或外部通知渠道。

## 测试

```powershell
cd server
conda activate Deep-Learning
$env:TEST_DATABASE_URL="postgresql+psycopg://smart_support:smart_support_dev@127.0.0.1:5432/smart_support"
python -m pytest -q

# 重新生成 3200 条问题并测试其中 1000 条
python scripts/generate_user_questions.py
python scripts/run_question_benchmark.py

cd ..\web
npm run build
```

测试会在 PostgreSQL 服务中创建隔离数据库，并在用例结束后删除；不会创建本地数据库文件。

## 旧数据一次性迁移

旧业务数据可使用离线工具迁移。执行前停止 API，目标 PostgreSQL 必须为空；LangGraph 旧检查点不会迁移。

```powershell
python ops/migrate_sqlite_to_postgres.py --source path/to/legacy.db --target postgresql+psycopg://user:password@host:5432/smart_support --dry-run
python ops/migrate_sqlite_to_postgres.py --source path/to/legacy.db --target postgresql+psycopg://user:password@host:5432/smart_support
```

## 项目结构

```text
SmartSupport-Agent/
├── knowledge-base/      # 虚构企业知识文档
├── ops/                 # Prometheus 规则与 Grafana provisioning/Dashboard
├── server/app/          # FastAPI、商城、Agent、RAG、认证、工单、申诉
├── server/tests/        # 自动测试
├── server/data/         # 合成用户提问数据
├── server/reports/      # 1000 条提问测试报告
├── web/src/             # React 顾客商城与员工客服后台
├── docs/                # 架构、部署和面试材料
└── docker-compose.yml
```

## 文档

- [系统架构](docs/ARCHITECTURE.md)
- [部署与配置](docs/DEPLOYMENT.md)
- [面试说明](docs/INTERVIEW_GUIDE.md)

## 真实边界

这是完整的求职作品集，不是已在真实企业流量中验证的商业产品。订单、物流和退款使用虚构数据；企业上线前仍需接入真实 CRM/OMS、密钥管理、对象存储、数据库迁移、备份恢复、告警渠道和安全审计平台。
