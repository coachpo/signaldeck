"""Exercise Actions build-context resolution without publishing images."""

import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ImageWorkflowTests(unittest.TestCase):
    def resolve(self, service):
        workflow = (ROOT / ".github/workflows/docker-images.yml").read_text()
        target = workflow.split("        id: target\n", 1)[1]
        script = target.split("        run: |\n", 1)[1].split("\n      - name:", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            result = subprocess.run(
                ["bash", "-eu", "-c", textwrap.dedent(script)],
                cwd=ROOT,
                env={
                    "PATH": os.environ["PATH"],
                    "SERVICE": service,
                    "GITHUB_OUTPUT": str(output),
                },
                capture_output=True,
                text=True,
                check=False,
            )
            values = (
                dict(line.split("=", 1) for line in output.read_text().splitlines())
                if output.exists()
                else {}
            )
        return result, values

    def test_all_targets_resolve_dockerfile_copy_sources(self):
        for service, context in (
            ("backend", "backend"),
            ("frontend", "frontend"),
            ("finance", "."),
            ("notes", "."),
            ("digital-oracle", "plugins"),
        ):
            with self.subTest(service=service):
                result, values = self.resolve(service)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    (ROOT / values["context"]).resolve(), (ROOT / context).resolve()
                )
                dockerfile = ROOT / values["file"]
                self.assertTrue(dockerfile.is_file())
                for source in re.findall(
                    r"^COPY (?!-)(.+) \S+$", dockerfile.read_text(), re.MULTILINE
                ):
                    for path in source.split():
                        self.assertTrue(
                            (ROOT / values["context"] / path).exists()
                            or list((ROOT / values["context"]).glob(path)),
                            f"{service}: COPY source {path} missing from context",
                        )

    def test_unknown_service_fails_before_build(self):
        result, values = self.resolve("unknown")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(values, {})


if __name__ == "__main__":
    unittest.main()
