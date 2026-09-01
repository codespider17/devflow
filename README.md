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
