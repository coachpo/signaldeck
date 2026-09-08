"""Project the latest completed network attempt for the selected plugin release."""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.plugin_catalog import PluginObservation
from app.infrastructure.platform_models import EvidenceRow, RunRow


class PluginHealthReader:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def latest(self, plugin_id: str, artifact_digest: str) -> PluginObservation:
        with self.sessions() as session:
            row = session.scalar(
                select(EvidenceRow.payload)
                .join(RunRow, EvidenceRow.run_id == RunRow.id)
                .where(
                    EvidenceRow.payload["kind"].astext == "attempt",
                    EvidenceRow.payload["toolId"].astext.startswith(
                        plugin_id + "/", autoescape=True
                    ),
                    EvidenceRow.payload["finishedAt"].astext.is_not(None),
                    RunRow.spec["pluginReleases"].contains(
                        [{"pluginId": plugin_id, "artifactDigest": artifact_digest}]
                    ),
                )
                .order_by(EvidenceRow.payload["finishedAt"].astext.desc(), EvidenceRow.id.desc())
                .limit(1)
            )
            if row is None:
                return PluginObservation()
            return PluginObservation(
                status=(
                    row["status"]
                    if row["status"] in {"succeeded", "failed", "unknown"}
                    else "unknown"
                ),
                observed_at=row["finishedAt"],
                error_code=row["errorCode"],
                run_id=row["runId"],
                operation_id=row["operationId"],
                evidence_id=row["id"],
            )
