"""Model credential identities are frozen while confirmed model receipts remain reusable."""

import asyncio
import os

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.tools import ToolDefinition
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from temporalio.testing import WorkflowEnvironment

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.model_runtime import RESPONSE, GatewayModel
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter, unpack_value
from app.infrastructure.temporal_services import TemporalServices
from app.infrastructure.tool_cache_store import ToolCacheRow
from app.workers.durable_worker import create_worker
from tests.test_durable_runtime_support import CORE, make_spec, model_server, tool_server


def test_model_rotation_rejects_old_identity_without_http_but_reuses_confirmed_receipt(
    database_url, tmp_path
):
    async def scenario():
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts")
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        store.save_resource("model", "model", {}, {"apiKey": "old-model-credential"})
        calls, events, credentials = [], [], []
        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=os.environ.get(
                    "TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal"
                ),
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            tool_server(events) as transport,
            model_server(calls, credential_log=credentials) as url,
        ):
            stale = make_spec(kind="model", model_url=url, model_store=store)
            store.create_run(stale, stale.run_id)
            old_revision = stale.model_bindings["model"]["credentialRevision"]
            store.save_resource("model", "model", {}, {"apiKey": "new-model-credential"})
            assert store.get_resource("model")["credentialRevision"] != old_revision
            services = TemporalServices(
                store, artifacts, lambda bindings: transport, CORE, lambda: None
            )
            async with await create_worker(environment.client, services, "model-credential-test"):

                async def execute(spec):
                    return await environment.client.execute_workflow(
                        "SignalDeckWorkflow",
                        spec.model_dump(mode="json", by_alias=True),
                        id=spec.run_id,
                        task_queue="model-credential-test",
                    )

                result = await execute(stale)
                assert result["status"] == "failed"
                assert calls == [] and events == []
                stale_detail = store.get_run(stale.run_id)
                model = next(e for e in stale_detail.evidence if e.kind == "model")
                assert model.error_code == "resource_binding_changed"
                with store.session_factory() as session:
                    assert session.scalar(select(func.count()).select_from(ToolCacheRow)) == 0

                current = make_spec(kind="model", model_url=url, model_store=store)
                store.create_run(current, current.run_id)
                assert (await execute(current))["status"] == "succeeded"
                assert credentials == ["Bearer new-model-credential"] * 2
                detail = store.get_run(current.run_id)
                confirmed = next(
                    e for e in detail.evidence if e.kind == "model" and e.status == "succeeded"
                )
                confirmed_input = unpack_value(artifacts, confirmed.input)
                store.save_resource("model", "model", {}, {"apiKey": "third-model-credential"})
                gateway = GatewayModel(store, store.resolve_bound_credentials, artifacts)
                # The receipt lookup precedes credential resolution. This path is used when
                # a committed model result needs replay after an Activity response was lost.
                receipt = await gateway.request(
                    ModelMessagesTypeAdapter.validate_python(confirmed_input["messages"]),
                    {
                        "signaldeck_context": {
                            "modelCallId": confirmed.id,
                            "runId": current.run_id,
                            "nodeId": "a",
                            "invocationId": confirmed.parent_id,
                            "resourceId": "model",
                            "binding": current.model_bindings["model"],
                            "deadline": current.deadline.isoformat(),
                        }
                    },
                    ModelRequestParameters(
                        function_tools=[
                            ToolDefinition(name=item["name"], parameters_json_schema=item["schema"])
                            for item in confirmed_input["tools"]
                        ]
                    ),
                )
                assert RESPONSE.dump_python(receipt, mode="json") == unpack_value(
                    artifacts, confirmed.output
                )
                assert len(calls) == 2
                fresh = make_spec(kind="model", model_url=url, model_store=store)
                assert (
                    fresh.model_bindings["model"]["credentialRevision"]
                    != current.model_bindings["model"]["credentialRevision"]
                )
                store.create_run(fresh, fresh.run_id)
                assert (await execute(fresh))["status"] == "succeeded"
                assert credentials[-2:] == ["Bearer third-model-credential"] * 2
                assert len(calls) == 4
                for spec in [stale, current, fresh]:
                    encoded = store.get_run(spec.run_id).model_dump_json()
                    assert all(
                        secret not in encoded
                        for secret in [
                            "old-model-credential",
                            "new-model-credential",
                            "third-model-credential",
                        ]
                    )
        engine.dispose()

    asyncio.run(scenario())
