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
