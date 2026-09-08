"""Regenerate bundled source and machine contracts from the importable demo YAML."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.definition_parser import parse_package_source  # noqa: E402


def main() -> None:
    sources: dict[str, str] = {}
    contracts = {}
    for path in sorted((ROOT / "demo").glob("*.yaml")):
        source = path.read_text(encoding="utf-8")
        compiled = parse_package_source(source)
        key = compiled.package.metadata.key
        if key != path.stem:
            raise ValueError("Demo filename must equal its package key")
        sources[key] = source
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
    target = ROOT / "backend/app/infrastructure/package_seeds.py"
    before, rest = target.read_text().split("# seed-sources:start\n", 1)
    _, after = rest.split("# seed-sources:end", 1)
    declaration = "_SOURCES: dict[str, str] = {\n"
    for key, source in sources.items():
        if '"""' in source or "\\" in source:
            raise ValueError("Embedded demo source must not require Python string escaping")
        declaration += f'    "{key}": """{source}""",\n'
    declaration += "}\n"
    target.write_text(
        before + "# seed-sources:start\n" + declaration + "# seed-sources:end" + after
    )
    (ROOT / "demo/contracts.json").write_text(
        json.dumps(contracts, indent=2, ensure_ascii=False) + "\n"
    )


if __name__ == "__main__":
    main()
