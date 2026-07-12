# UX-09 服务端 MVP 实施计划

> 实施时使用测试驱动和分任务交付。每个阶段必须通过本阶段门禁，再替换下一个原型数据模块。

**目标：** 将 UX-08 React 原型迁移为可在单服务器部署的 FastAPI + PostgreSQL + MinIO 招聘系统，并保持 F-01 至 F-06 的业务闭环和交互结构。

**架构：** 单租户模块化单体、服务端会话、服务端 RBAC、PostgreSQL 持久任务队列、独立 Worker、私有对象存储、Nginx HTTPS 入口。

**技术栈：** Python 3.12、FastAPI、SQLAlchemy 2、Alembic、Pydantic 2、PostgreSQL 16、MinIO、React 19、Vite 6、Docker Compose、Pytest、Playwright。

## 全局约束

- 不在业务表中复制候选人当前职位阶段；阶段属于申请。
- 不允许 AI 自动通过、淘汰、通知或删除候选人。
- 不将简历、联系方式、API Key 或会话写入日志和测试快照。
- 前端模块迁移期间保留 UX-08 场景数据，未迁移页面不得接半成品 API。
- 所有 schema 变更通过 Alembic；禁止应用启动时隐式建表。
- 所有关键写操作必须有权限、状态机、并发和审计测试。

---

## Phase 0：项目骨架与可运行基础

**新增目录：**

```text
server/
  app/
    api/
    core/
    db/
    modules/
    worker/
  migrations/
  tests/
deploy/
  compose.yaml
  nginx/
```

- [ ] 新建 FastAPI 应用、配置模型、结构化日志、`/health/live` 和 `/health/ready`。
- [ ] 配置 SQLAlchemy、Alembic、PostgreSQL、MinIO 客户端和测试数据库。
- [ ] 建立 `api`、`worker`、`postgres`、`minio`、`proxy` 的开发 Compose。
- [ ] CI 执行 Ruff、类型检查、Pytest、前端测试、构建和迁移检查。
- [ ] 验证无数据库时存活检查成功、就绪检查失败；依赖恢复后就绪检查自动恢复。

**门禁：** 空系统可由一条 Compose 命令启动；迁移可在空库执行；测试环境不依赖生产密钥。

## Phase 1：身份、会话和权限

- [ ] 先写登录、退出、超时、禁用账号、CSRF 和会话撤销失败测试。
- [ ] 实现组织、部门、用户、角色、职位协作者和服务端会话表。
- [ ] 实现 `POST /auth/login`、`POST /auth/logout`、`GET /me`。
- [ ] 实现统一权限策略和字段裁剪，不在路由内散落角色字符串判断。
- [ ] 角色、职位或人才库范围变化时递增权限版本并撤销旧会话。
- [ ] 建立五类角色的 API 权限矩阵测试，包括系统管理员无默认招聘数据权。
- [ ] 提供仅开发环境可用的合成账号 Seed，生产不创建默认密码。

**门禁：** 未登录 401、已登录越权 403、无数据摘要泄露；禁用用户的所有会话立即失效。

## Phase 2：职位、候选人、简历和申请

- [ ] 创建职位、JD/规则版本、候选人、联系方式、文件对象、简历、申请、阶段事件和审计迁移。
- [ ] 用数据库部分唯一索引阻止同候选人同职位重复活跃申请。
- [ ] 实现职位 CRUD、版本创建、协作者和职位状态转换。
- [ ] 实现候选人列表/详情、简历版本、预览、下载票据和人工修正。
- [ ] 实现申请创建、合法阶段流转、淘汰原因、人工结论和版本冲突。
- [ ] 迁移前端职位和候选人模块到 API；保留原型场景作为开发 Fixture。

**门禁：** 职位和候选人页面刷新后状态不丢失；同职位活跃重复返回 409；下载必须授权并产生审计。

## Phase 3：上传、解析、规则与 LLM

- [ ] 先写任务领取、租约过期、幂等重试、单文件失败和批次聚合测试。
- [ ] 实现 `background_jobs`、Worker 领取/续租/退避和任务管理命令。
- [ ] 实现任务尝试历史和事务 Outbox，验证业务提交后事件不会因进程崩溃丢失。
- [ ] 实现筛选批次、逐文件流式上传、MIME/magic/大小校验和隔离存储。
- [ ] 将现有 PDF/DOCX/TXT 提取迁入解析适配器，保留解析器版本和质量状态。
- [ ] 将现有 75/15/10 规则迁入版本化评分服务，加入 59 分封顶兼容测试。
- [ ] 实现 LLM Gateway、加密 Provider 配置、固定内容连接测试、脱敏与结构化响应校验。
- [ ] 对 Provider 使用部署白名单和出口限制，加入 SSRF、重定向和 DNS 重绑定测试。
- [ ] 实现任务进度、失败原因、文件级重试和批量人工动作 API。
- [ ] 迁移筛选页面到 API，显示稳定的“已处理/总数”和部分成功。

**门禁：** 100 份合成简历可在浏览器关闭和服务重启后继续；LLM 故障保留规则结果；AI 不触发申请状态命令。

## Phase 4：面试与反馈

- [ ] 建立面试、参与人、反馈、反馈修订和通知状态迁移。
- [ ] 实现时间冲突检查、面试创建/改期/取消/未到场和 ICS 生成。
- [ ] 实现面试官最小候选人快照和本人反馈草稿/提交。
- [ ] 所有必需反馈提交后，在同一事务中将申请推进到待决策。
- [ ] 提交失败时前端保留草稿；同一幂等键重复提交不产生重复反馈。
- [ ] 迁移面试列表、安排流程、候选人面试页和反馈页到 API。

**门禁：** 普通面试官不能读取他人草稿或无关候选人；改期不丢历史；ICS 可被主流日历解析。

## Phase 5：人才库、报表、设置和治理

- [ ] 实现人才库、成员关系、标签、检索和可见范围。
- [ ] 实现重新激活事务，创建新申请并引用来源申请；活跃重复返回 409。
- [ ] 实现授权范围内的漏斗、筛选质量、面试反馈和导出任务。
- [ ] 导出处理 CSV 公式注入并使用短期下载票据。
- [ ] 实现 LLM 设置、保留策略、审计查询和候选人删除任务。
- [ ] 实现法律保留和恢复后重新删除机制；普通应用数据库角色不能更新或删除审计事件。
- [ ] 迁移人才库、报表和设置页面到 API。

**门禁：** 入库不修改历史申请；报表和列表使用相同权限范围；删除影响清单覆盖数据库、对象和临时导出。

## Phase 6：生产化与端到端验收

- [ ] 完成生产 Compose、Nginx TLS、安全头、上传限制和仅内网依赖端口。
- [ ] 增加请求/任务 Trace、指标、告警、健康检查和容量监控。
- [ ] 编写安装、升级、回滚、备份、恢复、密钥轮换和故障排查 Runbook。
- [ ] 使用 UX-08 的 18 份合成简历执行 F-01 至 F-06 浏览器 E2E。
- [ ] 执行角色越权、任务恢复、LLM 降级、版本冲突、恶意上传和删除测试。
- [ ] 执行会话固定、CSRF、权限变化撤销、IDOR、LLM SSRF 和审计防篡改测试。
- [ ] 完成一次 PostgreSQL + MinIO 恢复演练并核对候选人、申请、反馈和附件一致性。
- [ ] 在 1280×720 和 390×844 验证迁移后的关键流程，不降低 UX-08 可用性基线。

**门禁：** P0/P1 缺陷为 0；所有自动检查通过；RPO 24 小时、RTO 4 小时恢复演练有证据；生产只暴露 HTTPS Web 入口。

## 推荐提交边界

1. `Bootstrap server runtime and deployment stack`
2. `Add secure sessions and recruiting RBAC`
3. `Persist jobs candidates resumes and applications`
4. `Add durable resume screening pipeline`
5. `Integrate interview scheduling and feedback`
6. `Persist talent pools reports and governance`
7. `Complete production deployment and E2E gates`

每个提交独立通过迁移、后端测试和受影响前端测试。不要在单个提交同时创建全部表、全部 API 和全部页面迁移。

## 最终验证命令（实施后）

```powershell
docker compose -f deploy/compose.yaml config
python -m alembic upgrade head
python -m pytest
npm test
npm run build
git diff --check
```

另需执行 Playwright E2E、API 权限矩阵、备份恢复和 100 份简历任务恢复测试；这些不能由单元测试替代。
