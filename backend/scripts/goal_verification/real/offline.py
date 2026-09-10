"""Capture historical read projections online and after owned Notes+Temporal stop.

No launches, operation queries or schedule mutations occur in this script. Browser
export/comparison rendering is a separate frontend check against these same runs.
"""

import argparse
import json
import socket
from copy import deepcopy
from urllib.parse import urlencode

from probe import OUT, compact, request


def pages(path, snapshot=None):
    output = []
    offset = 0
    while True:
        params = {"limit": 100, "offset": offset}
        if snapshot:
            params["snapshotAt"] = snapshot
        page = request(path + ("&" if "?" in path else "?") + urlencode(params))
        output.append(page)
        snapshot = page["snapshotAt"]
        offset += len(page["items"])
        if offset >= page["total"]:
            return output
        assert page["items"], "Pagination ended before reported total"


def stable_runs(rows):
    rows = deepcopy(rows)
    for row in rows:
        row["detail"]["usageProjection"].pop("asOf", None)
    return rows


def capture(label):
    if label == "double-offline":
        for port in (21082, 18233):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    pass
            except OSError:
                continue
            raise AssertionError(f"Port {port} is reachable; services are not double offline")
    rows = json.loads((OUT / "runs.json").read_text())
    before = (
        json.loads((OUT / "online-histories.json").read_text())
        if label == "double-offline"
        else None
    )
    result = {
        "runs": [],
        "history": pages("/runs", before["history"][0]["snapshotAt"] if before else None),
        "attention": pages(
            "/attention?view=all", before["attention"][0]["snapshotAt"] if before else None
        ),
    }
    for row in rows:
        rid = row["id"]
        result["runs"].append(
            {
                "id": rid,
                "label": row["label"],
                "detail": compact(request("/runs/" + rid), row["label"]),
                "result": request("/runs/" + rid + "/result"),
            }
        )
    (OUT / (label + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if label == "double-offline":
        state = json.loads((OUT / "control.json").read_text())
        assert {"Temporal dev server", "notes plugin"} <= set(
            state.get("stopped", [])
        ), "Owned services must actually be stopped"
        assert stable_runs(before["runs"]) == stable_runs(
            result["runs"]
        ), "Historical run/result/usage projections changed while offline"
        assert before["history"] == result["history"], "History projection changed while offline"
        assert (
            before["attention"] == result["attention"]
        ), "Attention projection changed while offline"
    print(json.dumps({"label": label, "readableRuns": len(result["runs"])}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("label", choices=["online-histories", "double-offline"])
    capture(parser.parse_args().label)
