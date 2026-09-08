# DevFlow端到端项目终验报告

验收日期：2026-09-08

## 验收范围

- GitHub代码、Jenkins流水线、Trivy安全门禁、Harbor私有镜像、K3s与Helm发布。
- 人工审批、状态回写、失败回滚、审计事件、Prometheus指标与Grafana Dashboard。

## 成功发布证据

- Deployment ID：84fa4504-17b6-4e20-a435-f7b19af414fc
- Pipeline Run ID：bcb6779a-bc45-4040-b78d-01f680d5e6da
- 状态：succeeded
- 镜像：hb.reg.com/devflow/devflow-api:ec6845038355582598a6dc52d930714cf0c7bee9
- 审计链：requested -> approved -> deploying -> succeeded

## 失败回滚证据

- Deployment ID：94b9f310-1e4d-4dda-87ce-62e251f9062a
- Pipeline Run ID：2c408b2f-15f3-4ae8-8a9d-dd8f76a05322
- 失败镜像：hb.reg.com/devflow/devflow-api:944eac903a03b433611ca712b5300ed3591e82b1
- 恢复镜像：hb.reg.com/devflow/devflow-api:febef9db53c69c75e5ed620981a8dad594428942
- 状态：rolled_back
- 审计链：requested -> approved -> deploying -> failed -> rolled_back

## 可观测性证据

- Prometheus中的DevFlow API与Jenkins采集目标均为up。
- DevFlow流水线、发布、Webhook及Jenkins执行器指标均可查询。
- Grafana Dashboard UID：devflow-platform-overview，面板数量：8。

## 最终结论

DevFlow端到端交付、审批发布、自动回滚、审计和可观测性闭环通过真实证据终验。
