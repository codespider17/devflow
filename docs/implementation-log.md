# DevFlow实施记录

## 2026-09-01 M0：环境准备

- 完成Ubuntu Server 26.04 LTS环境检查。
- 根文件系统扩展至97GiB，可用84GiB。
- 创建并持久化4GiB Swap。

## 2026-09-01 M1：GitHub准备

- 安装基础运维开发工具。
- 配置Git提交身份和ED25519密钥。
- 使用SSH 443端口连接GitHub。
- 初始化DevFlow项目仓库。

## 2026-09-01 M2：Docker与Jenkins运行环境

- 使用Docker官方APT仓库安装Docker Engine、Buildx和Compose。
- 构建Jenkins LTS JDK 21自定义镜像并预装流水线插件。
- 使用Docker Compose部署Jenkins，命名卷持久化数据。
- 验证Jenkins Web、插件、单执行器和Docker CLI能力。

## 2026-09-01 M3：K3s与Helm运行环境

- 部署单节点K3s并禁用内置Traefik和ServiceLB。
- 验证CoreDNS、metrics-server和local-path默认存储类。
- 安装Helm并验证与K3s集群连接。
- 创建平台、应用和监控三个基础命名空间。

## 2026-09-01 M4：FastAPI与PostgreSQL基础平台

- 创建FastAPI工程基线、健康接口、就绪接口和OpenAPI文档。
- 使用Docker Compose运行PostgreSQL 17，端口仅绑定127.0.0.1，并使用命名卷持久化数据。
- 实现SQLAlchemy核心数据模型，并通过Alembic完成首次数据库迁移。
- 实现Project、Environment和Pipeline Run基础API。
- Ruff、Alembic一致性、9个pytest测试、PostgreSQL事务回滚和OpenAPI契约检查全部通过。
- 数据库密码仅保存在本地.env中，未加入Git仓库。

## 2026-09-01 M4：FastAPI、PostgreSQL与K3s部署

- 完成FastAPI基础服务、PostgreSQL持久化、SQLAlchemy模型和Alembic迁移。
- 完成Project、Environment和Pipeline Run基础API及PostgreSQL事务集成测试。
- 构建`devflow-api:0.1.0`非root镜像，并通过只读根文件系统、禁止提权、资源限制和数据库就绪验收。
- 使用Helm部署API Deployment、Service、ServiceAccount和PostgreSQL StatefulSet、Secret、2Gi RWO PVC及NetworkPolicy。
- 解决K3s local-path卷初始目录权限与PostgreSQL固定UID 70不兼容的问题，通过受控`data-permissions` initContainer完成目录所有权初始化。
- Helm Release `devflow`部署成功，API和PostgreSQL Pod均达到`1/1 Running`。
- 完成Project、Environment和Pipeline Run真实API工作流验证。
- 删除并重建API Pod和PostgreSQL Pod后，同一Pipeline Run仍可查询，PVC UID保持不变，持久化验证通过。
- API ServiceAccount无Secret读取权限，PostgreSQL仅允许DevFlow API Pod访问5432。
- M4最终验收：通过。

## 2026-09-01 M5-A：GitHub Webhook安全接入

- 新增GitHub Webhook Delivery模型、唯一Delivery ID约束和Alembic迁移。
- 实现HMAC-SHA256常量时间签名校验、1MiB请求体限制和JSON对象校验。
- 实现ping、push事件接收，其他事件记录为ignored。
- 实现Delivery ID幂等去重，同一Delivery只保存一条数据库记录。
- 不持久化完整Webhook正文，只保留事件类型、仓库、Git引用和Commit SHA等最小元数据。
- M5-A自动化测试与安全边界验收通过。

## 2026-09-01 M5-B：Jenkins客户端与Pipeline骨架

完成Jenkins参数化构建客户端与Declarative Pipeline骨架，实现Folder/Job路径编码、Basic Auth、参数表单编码、超时与异常脱敏。

Pipeline包含单并发、20分钟超时、显式Checkout和Docker运行环境检查；Jenkins API Token仅保存在本机忽略文件中，不进入公开仓库。

Jenkins客户端专项测试4个，全量测试21个；Ruff、pip check和Alembic一致性检查通过。真实服务账号和SCM Job触发在下一阶段单独验收。

## 2026-09-02 M5-C：Webhook事件编排与Jenkins真实触发

完成GitHub Webhook与Pipeline Run编排服务接线。默认分支push在完成HMAC-SHA256签名验证、Delivery幂等检查、仓库匹配和环境选择后创建`trigger_source=github`的Pipeline Run，并通过服务账号调用Jenkins参数化构建接口。

新增Pipeline Run触发来源、Jenkins队列URL、脱敏触发错误和Webhook关联字段，数据库迁移版本升级到`f411f2e069b3`。覆盖正常触发、重复Delivery、非默认分支、未注册仓库、缺少环境、ping事件和Jenkins失败等路径。

真实签名push成功触发Jenkins构建3并获得`SUCCESS`，重复投递返回同一Pipeline Run且未增加构建。Webhook专项8个测试及全量30个测试通过，Ruff、pip check和Alembic模型一致性检查通过。

## 2026-09-02 M5-D：Jenkins构建状态回写闭环

完成受Bearer Token保护的Pipeline Run状态回写接口与严格状态机，Callback Token通过Jenkins Secret Text凭据注入，不写入Jenkinsfile或公开配置。

覆盖running、succeeded、failed、cancelled、重复回写、非法转换、终态保护、错误Token和未知Run等路径，状态回写专项7个测试及全量37个测试通过。

真实签名push触发Jenkins构建4，Pipeline Run c8243103-7bcb-47cb-9ca7-8514db8865b9 自动记录started_at和finished_at并进入succeeded；重复Delivery未增加构建。
