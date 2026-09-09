"""Regenerate machine contracts from the importable demo YAML."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.definition_parser import parse_package_source  # noqa: E402


def main() -> None:
    contracts = {}
    for path in sorted((ROOT / "demo").glob("*.yaml")):
        source = path.read_text(encoding="utf-8")
        compiled = parse_package_source(source)
        key = compiled.package.metadata.key
        if key != path.stem:
            raise ValueError("Demo filename must equal its package key")
        contracts[key] = {
            "contentHash": compiled.content_hash,
            "tools": sorted(
                {tool for agent in compiled.package.agents.values() for tool in agent.tools}
            ),
            "resources": sorted(
                {ref for agent in compiled.package.agents.values() for ref in agent.resources}
            ),
            "plans": {
                name: plan.model_dump(mode="json", by_alias=True)
                for name, plan in compiled.plans.items()
            },
        }
    (ROOT / "demo/contracts.json").write_text(
        json.dumps(contracts, indent=2, ensure_ascii=False) + "\n"
    )


if __name__ == "__main__":
    main()
