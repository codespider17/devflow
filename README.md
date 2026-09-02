# DevFlow

DevFlow是面向运维开发场景设计的云原生持续交付与研发效能平台，目标是贯通代码变更、质量检查、镜像构建、安全扫描、制品入库、Kubernetes发布、健康验证、审批回滚和审计度量流程。

## 规划架构

```text
GitHub
  -> Jenkins Pipeline
  -> 代码检查与自动化测试
  -> Docker镜像构建
  -> Trivy安全扫描
  -> Harbor制品仓库
  -> Helm发布到K3s
  -> 健康检查、审批与回滚
  -> Prometheus与Grafana效能度量
```

## Jenkins运行环境

- 基于Jenkins LTS JDK 21构建自定义控制器镜像。
- 容器内集成Docker CLI、Buildx和Compose。
- 使用命名卷持久化Jenkins Home，并限制为单执行器。
- 通过Docker Socket支持后续镜像构建流水线。

## Kubernetes运行环境

- 使用单节点K3s提供持续交付目标环境。
- K3s内置containerd与宿主机Docker Engine并行运行。
- 使用Helm管理后续平台组件和应用版本。
- 划分devflow-system、devflow-apps和monitoring命名空间。

## FastAPI与PostgreSQL基础平台

- 基于FastAPI提供健康检查、就绪检查和OpenAPI接口文档。
- 使用SQLAlchemy 2管理Project、Environment和Pipeline Run核心数据模型。
- 使用Alembic管理PostgreSQL数据库版本和结构迁移。
- 支持Project创建与查询、Environment创建、Pipeline Run创建与详情查询。
- 使用Ruff、pytest、PostgreSQL外层事务和OpenAPI契约检查完成自动化验收。

## Kubernetes集群部署

DevFlow API已完成容器化并通过Helm部署到单节点K3s。部署内容包括FastAPI Deployment、ClusterIP Service、最小权限ServiceAccount，以及PostgreSQL StatefulSet、Secret、2Gi RWO PVC和数据库入站NetworkPolicy。

部署流程使用Alembic initContainer自动执行数据库迁移；API和PostgreSQL均配置健康检查、资源限制、禁止提权和非root运行。PostgreSQL通过受控权限初始化容器适配K3s local-path卷，主容器固定使用UID/GID 70。

实际验收已覆盖Project、Environment和Pipeline Run接口工作流、API Pod重建、PostgreSQL Pod重建及PVC持久化。Pod重建后Pipeline Run数据仍可查询，证明应用状态由PostgreSQL持久化保存。

主要部署文件：

- `Dockerfile`：DevFlow API多阶段、非root容器镜像。
- `.dockerignore`：限制构建上下文和敏感文件进入镜像。
- `deploy/helm/devflow/`：API、PostgreSQL、PVC、ServiceAccount和NetworkPolicy的Helm Chart。

## 安全Webhook接入

DevFlow实现GitHub Webhook安全接入基线：使用HMAC-SHA256验证请求签名，通过X-GitHub-Delivery实现幂等去重，并限制请求体最大为1MiB。当前接收ping和push事件，其他事件保存最小审计元数据后标记为ignored，不持久化完整Webhook正文。

## Jenkins流水线基线

- 提供参数化Declarative Pipeline骨架，接收Pipeline Run ID和Git Commit SHA。
- 提供Jenkins参数化构建客户端，支持Folder/Job路径编码、Basic Auth和超时控制。
- Jenkins URL禁止内嵌用户名密码，客户端异常信息不回显API Token。
- Pipeline启用单并发、执行超时、显式Checkout和Docker运行环境检查。

## GitHub事件驱动流水线

DevFlow已实现从GitHub Webhook到Jenkins Pipeline的事件驱动触发链路：使用HMAC-SHA256校验Webhook签名，通过Delivery ID进行幂等去重，仅对已注册仓库的默认分支push创建Pipeline Run，并将Run ID和Git提交作为参数传递给Jenkins。

平台会审计Webhook、Pipeline Run、Jenkins队列URL和脱敏失败原因。真实闭环测试中，签名push成功进入Jenkins队列并完成构建；同一Delivery重复投递返回原Pipeline Run，未产生重复构建。
