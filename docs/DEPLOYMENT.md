# 部署与配置

## 必须更换的配置

```dotenv
AUTH_SECRET=至少32位随机字符串
LLM_API_KEY=DeepSeek密钥
DATABASE_URL=postgresql+psycopg://user:password@host:5432/database
REDIS_URL=redis://host:6379/0
OFF_TOPIC_MAX_CONSECUTIVE_QUESTIONS=3
OFF_TOPIC_WINDOW_SECONDS=1800
INTENT_ROUTER_MIN_CONFIDENCE=0.65
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=至少16位随机字符串
```

不要提交 `.env`。生产环境应使用云平台 Secret、Vault 或 Kubernetes Secret。

## 本地基础设施

- PostgreSQL/pgvector：`127.0.0.1:5432/smart_support`
- LangGraph：同一 PostgreSQL 数据库中的专用 checkpoint 表
- 上传文件：`server/data/uploads/`
- Embedding：Hugging Face 用户缓存

使用 `docker compose up -d db redis` 启动本地依赖。应用拒绝非 `postgresql+psycopg://` 的 `DATABASE_URL`，本地和测试环境不会静默降级为文件数据库。

## Docker 服务

| 服务 | 端口 | 用途 |
|---|---:|---|
| web | 5173 | Nginx + React |
| server | 8000 | FastAPI |
| db | 5432 | PostgreSQL + pgvector |
| redis | 内部 | 共享限流 |
| prometheus | 9090 | 指标采集 |
| grafana | 3000 | 监控看板 |

示例密码仅用于本地 Compose。公开部署前必须通过环境变量或 Secret 替换。

## Agent 语义路由

Support Orchestrator 使用三级混合路由。第一层由确定性规则直接处理订单号加订单查询、物流、明确退款办理、问候、人工请求和强风险信号；第二层仅在规则无法确定时调用 DeepSeek，要求返回受控的 `route`、`intent`、`confidence`、`entities`、候选冲突意图和澄清标记；第三层由代码校验并决策。高置信度结果进入对应 Agent，多意图冲突和普通低置信度结果进入补问节点，高风险低置信度结果转人工，模型超时或 JSON 解析失败则回退到关键词路由。

模型抽取的订单号和商品号只是候选实体，必须先通过格式校验，随后仍由业务工具执行用户归属、权限和状态检查。`route` 与 `intent` 不一致时整个模型结果视为无效，Agent 映射以确定性代码为准。路由 Trace 会记录意图、来源、置信度和理由。

## 无关问题资源保护

系统在调用 LangGraph 和 DeepSeek 前，使用确定性规则识别明显偏离商城客服范围的问题，并按用户会话在 Redis 中累计。默认允许连续 3 次无关问题，第 4 次起直接返回资源保护提示，不再调用 Agent、RAG 或大模型。计数默认保留 30 分钟；用户重新咨询商品、订单、物流、售后、账号或申诉等业务问题后立即清零。Redis 不可用时，单实例进程内计数作为降级方案。

## 语义知识缺口

`KNOWLEDGE_GAP_SIMILARITY_THRESHOLD` 默认 `0.82`，控制相同商品下未覆盖问题的合并阈值。`KNOWLEDGE_GAP_BACKFILL_LIMIT` 默认 `200`，控制质量看板每次读取时最多补偿处理的中断任务数。问题文本、用户 ID、会话 ID 和商品 ID 不作为 Prometheus 标签。

旧业务库只允许通过 `ops/migrate_sqlite_to_postgres.py` 离线迁移。工具支持 `--dry-run`、目标非空保护、按外键顺序复制与序列重置；旧 LangGraph checkpoint 明确不迁移。

## 可观测体系

FastAPI 在 `/metrics` 暴露 Prometheus 格式指标，Prometheus 每 15 秒采集一次。指标标签只包含固定的路由模板、Agent 路由、执行状态、模型、检索模式和工具名，不记录用户 ID、会话 ID、订单号或问题内容。

| 监控域 | 指标内容 |
|---|---|
| HTTP | 请求量、状态码、进行中请求、P50/P95/P99 延迟 |
| Agent | 路由、执行结果、耗时、置信度、人工介入率 |
| LLM | 同步/流式调用、成功率、完整耗时、首 Token、API 返回的 Token 用量 |
| RAG | 关键词/混合检索、命中率、耗时、返回分段数 |
| Tool | 订单、物流、退款工具的成功、业务拦截、异常与耗时 |
| Runtime | Python 进程 CPU、内存与 Prometheus target 状态 |

Grafana provisioning 会自动创建 `Prometheus` 数据源，并从 `ops/grafana/dashboards` 加载 `SmartSupport Agent Overview`。启动后访问 `http://127.0.0.1:3000`，Dashboard 位于 `SmartSupport` 文件夹。

Prometheus 默认加载以下告警规则：

- API 连续 2 分钟不可采集；
- HTTP 5xx 比例连续 10 分钟超过 5%；
- HTTP P95 延迟连续 10 分钟超过 5 秒；
- 10 分钟内至少 5 次模型调用且错误率超过 10%；
- 10 分钟内至少 10 次检索且未命中率超过 30%；
- 10 分钟内工具调用被拦截或异常达到 3 次。

这些规则显示在 Prometheus 和 Grafana 中，但当前没有部署 Alertmanager，因此不会发送邮件、短信或 Webhook。生产部署应接入企业告警渠道，并根据真实流量重新校准阈值。

当前 Compose 使用单个 Uvicorn worker。扩展为多 worker 时，需要先按 `prometheus_client` multiprocess 模式调整指标目录、进程生命周期和采集配置，避免计数不完整。

## 上线前检查

- 执行数据库迁移，而不是仅依赖 `create_all`。
- 将上传文件迁移到 S3/OSS/MinIO。
- 配置 HTTPS、反向代理和可信代理头。
- 配置 PostgreSQL 与上传文件备份。
- 接入 Alertmanager/企业通知渠道、日志聚合和密钥轮换。
- 使用真实 CRM/OMS 沙箱执行集成测试。
