# 后端全范围盘点与保留决策

CI backend-quality 执行 `uv run pytest`，不分层过滤；同一入口包含纯单元、真实PostgreSQL集成、Temporal/独立进程、provider合约及Notes Chromium UI。未配置coverage或变异测试依赖/命令。本轮无需引入新基础设施。

共 69 个 test_*.py 文件，532 个静态测试函数，877 个收集节点；test_durable_runtime_support.py 为零节点的共享协议服务器模块。所有节点见 sd-backend-collect.log；全部函数/行号/参数/直接导入/fixture/断言计数见 sd-backend-inventory.json。

| 测试文件 | 收集节点 | 行为/风险映射 | 消融评估 |
|---|---:|---|---|
| backend/tests/test_agent_deadline_classification.py | 1 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_agent_initial_projection.py | 1 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_agent_response_contract.py | 38 | A03/A04/A06/A13/A14/A18：闭合包/schema、YAML安全、推导DAG边、缺失与响应根边界 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_artifact_store_target.py | 5 | A07/A10/A15：不可变Core/内容寻址制品、隔离环境与完整性 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_auth_middleware.py | 6 | A14 / HTTP合同：401/CORS、错误脱敏、路由404/405、数据库URL与运行配置 | 实际故障实验；候选减少重复数据库setup并保留HTTP断言 |
| backend/tests/test_core_api.py | 4 | A14 / HTTP合同：401/CORS、错误脱敏、路由404/405、数据库URL与运行配置 | 实际故障实验；候选减少重复数据库setup并保留HTTP断言 |
| backend/tests/test_core_artifacts.py | 14 | A07/A10/A15：不可变Core/内容寻址制品、隔离环境与完整性 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_dag_compiler.py | 34 | A03/A04/A06/A13/A14/A18：闭合包/schema、YAML安全、推导DAG边、缺失与响应根边界 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_db_engine.py | 6 | A14 / HTTP合同：401/CORS、错误脱敏、路由404/405、数据库URL与运行配置 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_demo_presentation.py | 7 | D01–D06/A04/A10：声明与散列兼容、演示数据流、导入原子性、冻结展示和链接归属 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_demo_workflow_dataflow.py | 13 | D01–D06/A04/A10：声明与散列兼容、演示数据流、导入原子性、冻结展示和链接归属 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_durable_runtime.py | 2 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_durable_runtime_boundaries.py | 1 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_durable_runtime_budgets.py | 2 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_durable_runtime_cache.py | 1 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_durable_runtime_cancel.py | 3 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_durable_runtime_credentials.py | 1 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_durable_runtime_dynamic_catalog.py | 3 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_durable_runtime_injection.py | 1 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_durable_runtime_plugin_stop.py | 4 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_durable_runtime_support.py | 0 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_effect_projection.py | 14 | A08/A09/A11/A13/A14/A15：逻辑写效果与网络attempt、并发工具恢复、缓存来源和TTL、资源租约 | 实际参数消融；缺失/冲突契约按故障独有检出决定保留 |
| backend/tests/test_encrypted_jsonb.py | 3 | A14 / HTTP合同：401/CORS、错误脱敏、路由404/405、数据库URL与运行配置 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_execution_budgets.py | 17 | A03/A10/A13/A15：预算独立性、调用/网络用量、冻结provider契约、实际SDK协议、诊断 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_execution_projection.py | 8 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_execution_tracing.py | 6 | A10/A12/A14/A15：公开API、冻结启动、事务/证据一致性、追踪与脱敏 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_fake_openai_provider.py | 3 | A03/A10/A13/A15：预算独立性、调用/网络用量、冻结provider契约、实际SDK协议、诊断 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_finance_api.py | 37 | A01/A02/A13/A14/A18：独立插件合同与进程、提供商适配、业务数据/事务所有权 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_finance_conflicts.py | 2 | A01/A02/A13/A14/A18：独立插件合同与进程、提供商适配、业务数据/事务所有权 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_finance_providers.py | 156 | A01/A02/A13/A14/A18：独立插件合同与进程、提供商适配、业务数据/事务所有权 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_formatting.py | 2 | A14 / HTTP合同：401/CORS、错误脱敏、路由404/405、数据库URL与运行配置 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_independent_plugins.py | 11 | A01/A02/A13/A14/A18：独立插件合同与进程、提供商适配、业务数据/事务所有权 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_local_postgres_bootstrap.py | 4 | A14 / HTTP合同：401/CORS、错误脱敏、路由404/405、数据库URL与运行配置 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_mcp_cancellation.py | 4 | A08/A09/A11/A13/A14/A15：逻辑写效果与网络attempt、并发工具恢复、缓存来源和TTL、资源租约 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_model_activity_recovery.py | 2 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_model_budget_contract.py | 55 | A03/A10/A13/A15：预算独立性、调用/网络用量、冻结provider契约、实际SDK协议、诊断 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_model_budget_failures.py | 8 | A03/A10/A13/A15：预算独立性、调用/网络用量、冻结provider契约、实际SDK协议、诊断 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_model_diagnostics.py | 16 | A03/A10/A13/A15：预算独立性、调用/网络用量、冻结provider契约、实际SDK协议、诊断 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_model_output_enforcement.py | 31 | A03/A10/A13/A15：预算独立性、调用/网络用量、冻结provider契约、实际SDK协议、诊断 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_model_usage.py | 5 | A03/A10/A13/A15：预算独立性、调用/网络用量、冻结provider契约、实际SDK协议、诊断 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_model_usage_runtime.py | 2 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_notes_browser.py | 1 | Notes业务/UI：真实资料来源导航、隔离记录、字面搜索和事务回滚 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_notes_workspace.py | 4 | Notes业务/UI：真实资料来源导航、隔离记录、字面搜索和事务回滚 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_operation_redelivery.py | 1 | A08/A09/A11/A13/A14/A15：逻辑写效果与网络attempt、并发工具恢复、缓存来源和TTL、资源租约 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_oracle_fred_provider.py | 7 | A01/A02/A13/A14/A18：独立插件合同与进程、提供商适配、业务数据/事务所有权 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_oracle_providers.py | 88 | A01/A02/A13/A14/A18：独立插件合同与进程、提供商适配、业务数据/事务所有权 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_platform_api.py | 8 | A10/A12/A14/A15：公开API、冻结启动、事务/证据一致性、追踪与脱敏 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_platform_persistence.py | 19 | A10/A12/A14/A15：公开API、冻结启动、事务/证据一致性、追踪与脱敏 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_plugin_sessions.py | 2 | A01/A02/A13/A14/A18：独立插件合同与进程、提供商适配、业务数据/事务所有权 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_plugin_wire_contracts.py | 3 | A03/A04/A06/A13/A14/A18：闭合包/schema、YAML安全、推导DAG边、缺失与响应根边界 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_presentation_binding.py | 5 | D01–D06/A04/A10：声明与散列兼容、演示数据流、导入原子性、冻结展示和链接归属 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_presentation_contract.py | 29 | D01–D06/A04/A10：声明与散列兼容、演示数据流、导入原子性、冻结展示和链接归属 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_repeat_workflow_cancellation.py | 1 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_resource_limiter.py | 6 | A08/A09/A11/A13/A14/A15：逻辑写效果与网络attempt、并发工具恢复、缓存来源和TTL、资源租约 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_result_declarations.py | 30 | D01–D06/A04/A10：声明与散列兼容、演示数据流、导入原子性、冻结展示和链接归属 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_result_failure_details.py | 6 | 普通任务/历史合同：准备绑定、跨页查询、草稿/常用配置、乐观冲突、结果错误与离线读取 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_result_organizer.py | 7 | 普通任务/历史合同：准备绑定、跨页查询、草稿/常用配置、乐观冲突、结果错误与离线读取 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_run_title_declarations.py | 2 | D01–D06/A04/A10：声明与散列兼容、演示数据流、导入原子性、冻结展示和链接归属 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_runtime_config_health.py | 9 | A14 / HTTP合同：401/CORS、错误脱敏、路由404/405、数据库URL与运行配置 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_target_schedules.py | 18 | A17/A12/A09：计划原子outbox、重放、重叠、时间窗口与DST | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_target_seeds.py | 10 | D01–D06/A04/A10：声明与散列兼容、演示数据流、导入原子性、冻结展示和链接归属 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_task_drafts.py | 6 | 普通任务/历史合同：准备绑定、跨页查询、草稿/常用配置、乐观冲突、结果错误与离线读取 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_task_experience.py | 24 | 普通任务/历史合同：准备绑定、跨页查询、草稿/常用配置、乐观冲突、结果错误与离线读取 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_task_presets.py | 8 | 普通任务/历史合同：准备绑定、跨页查询、草稿/常用配置、乐观冲突、结果错误与离线读取 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_terminal_projection_cancellation.py | 2 | A03/A05–A11/A16：真实Temporal/独立worker/网络/插件进程、恢复及取消（跨层不可替代） | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_tool_cache.py | 12 | A08/A09/A11/A13/A14/A15：逻辑写效果与网络attempt、并发工具恢复、缓存来源和TTL、资源租约 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_tool_gateway_overlap.py | 2 | A08/A09/A11/A13/A14/A15：逻辑写效果与网络attempt、并发工具恢复、缓存来源和TTL、资源租约 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_tool_gateway_target.py | 29 | A08/A09/A11/A13/A14/A15：逻辑写效果与网络attempt、并发工具恢复、缓存来源和TTL、资源租约 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |
| backend/tests/test_tool_gateway_unknown_reconcile.py | 5 | A08/A09/A11/A13/A14/A15：逻辑写效果与网络attempt、并发工具恢复、缓存来源和TTL、资源租约 | 纳入基线与合同评估；未对该组实施消融，独有价值未排除，保留 |

## 公共支持与历史依据

- conftest.py：autouse 清理 API token/settings；database_url 对真实PostgreSQL逐测试创建UUID库并清理；session_factory重置连接缓存；app初始化PlatformStore/ScheduleStore；client启动真实FastAPI中间件。替换数据库setup仅限不读数据库的404与合成API错误路由。
- platform_api.platform_environment、task_experience.platform、target_schedules.stores、platform_persistence.store：配置真实事务/不可变制品/调度适配；多文件复用，不能根据重复fixture外观删除。
- durable_runtime_support.py 的 tool_server/model_server/serve_app 提供本地协议服务器；fake_openai_provider.py为受控SDK兼容服务；fixtures/held_plugin.py验证独立进程停止。
- fixtures/dispatch_brief.yaml 是包合同；13个 digital_oracle JSON 供应商成功/空值/异常固定响应；notes_1_1 两份文本为历史制品兼容材料。无 pytest skip/xfail/importorskip；未发现专用pytest快照插件。模型快照/不可变运行快照是产品合同，不是图片黄金快照。
- test_notes_browser.py 真实调用 pnpm build:plugin-ui + plugins/notes/tests/browser.mjs (Chromium)，保护资料来源交互。其自动化通过不等于完整UI体验验证。
- 历史git依据：auth测试相关14b34cad（可选Bearer认证）、804101f8（非ASCII auth干净401）；core_api/初始DAG合同7285cecd；effect_projection相关617be93c（model/notes验证缺口）。保留非ASCII与只读历史边界。
- 现有能力边界：提供商使用MockTransport/固定响应，不证明真实外部服务可用；线程/Temporal/网络取消的真实故障不可由纯函数覆盖替代；行覆盖无现有配置，未用行数或相同实现路径作为删除依据。
