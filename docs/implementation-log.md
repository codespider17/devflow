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
