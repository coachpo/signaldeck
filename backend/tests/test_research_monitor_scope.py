"""Collection supersets do not silently expand the requested monitoring scope."""

from copy import deepcopy

from tests import test_research_monitor as support
from tests.test_research_monitor import begin, call, observation

runtime = support.runtime


def test_unselected_collection_is_stored_but_not_compared(runtime):
    first = begin(runtime)
    call(runtime, "monitor_observe", observation(first))
    second = begin(runtime)
    payload = observation(second)
    for source in ("news", "valuation"):
        extra = deepcopy(payload["evidence"][0])
        extra.update(evidenceId=source, sourceId=source, value="999", verified=False)
        payload["evidence"].append(extra)
        payload["coverage"].append(
            dict(
                sourceId=source, complete=False, observedAt=second["cutoffAt"], evidenceIds=[source]
            )
        )
    result = call(runtime, "monitor_observe", payload)
    assert result["state"] == "unchanged"
    assert result["changes"] == []
    assert result["warnings"] == []
    third = begin(runtime)
    payload["snapshotId"] = third["snapshotId"]
    payload["coverage"][0]["complete"] = False
    result = call(runtime, "monitor_observe", payload)
    assert result["state"] == "invalid"
    assert "required_source_invalid:sec" in result["warnings"]


def test_vintage_known_by_date_uses_completed_new_york_day(runtime):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    first = begin(runtime)
    payload = observation(first)
    item = payload["evidence"][0]
    item.pop("publishedAt")
    ny_date = (
        datetime.fromisoformat(first["cutoffAt"]).astimezone(ZoneInfo("America/New_York")).date()
    )
    item["availableByDate"] = (ny_date - timedelta(days=1)).isoformat()
    assert call(runtime, "monitor_observe", payload)["state"] == "no_baseline"
    second = begin(runtime)
    payload["snapshotId"] = second["snapshotId"]
    item["availableByDate"] = ny_date.isoformat()
    assert call(runtime, "monitor_observe", payload)["state"] == "invalid"
    third = begin(runtime)
    payload["snapshotId"] = third["snapshotId"]
    item["availableByDate"] = (ny_date + timedelta(days=1)).isoformat()
    assert call(runtime, "monitor_observe", payload)["state"] == "invalid"
