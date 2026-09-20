"""Check that both workflows build the one image from a context that holds its sources."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    (".github/workflows/docker-images.yml", "Build and push Docker image (linux/arm64)"),
    (".github/workflows/ci.yml", "Build the single application image"),
)


def build_step(workflow, step):
    text = (ROOT / workflow).read_text()
    body = text.split(f"- name: {step}\n", 1)[1].split("\n      - name:", 1)[0]
    return dict(
        re.findall(r"^\s{10}(context|file|tags|images):\s*(\S+)\s*$", body, re.MULTILINE)
    )


class ImageWorkflowTests(unittest.TestCase):
    def test_workflows_build_one_image_from_the_repository_root(self):
        for workflow, step in WORKFLOWS:
            with self.subTest(workflow=workflow):
                values = build_step(workflow, step)
                self.assertEqual(values["context"], ".")
                self.assertEqual(values["file"], "./Dockerfile")

    def test_published_image_name_has_no_plugin_variants(self):
        workflow = (ROOT / ".github/workflows/docker-images.yml").read_text()
        self.assertIn(
            "images: ${{ env.REGISTRY }}/${{ github.repository_owner }}/signaldeck\n",
            workflow,
        )
        self.assertNotIn("signaldeck-finance", workflow)
        self.assertNotIn("signaldeck-notes", workflow)
        self.assertNotIn("signaldeck-digital-oracle", workflow)

    def test_dockerfile_copy_sources_exist_in_the_build_context(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        for source in re.findall(r"^COPY (?!--)(.+) \S+$", dockerfile, re.MULTILINE):
            for path in source.split():
                with self.subTest(path=path):
                    self.assertTrue(
                        (ROOT / path).exists() or list(ROOT.glob(path)),
                        f"COPY source {path} missing from the build context",
                    )

    def test_application_and_plugin_runtimes_share_one_base_and_uv(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        bases = re.findall(r"^FROM (\S+)", dockerfile, re.MULTILINE)
        self.assertEqual(len({base for base in bases if "python" in base}), 1)
        self.assertEqual(len(set(re.findall(r"astral-sh/uv:(\S+?) ", dockerfile))), 1)
        for project in ("finance", "notes", "digital_oracle"):
            with self.subTest(project=project):
                self.assertFalse((ROOT / "plugins" / project / "Dockerfile").exists())


if __name__ == "__main__":
    unittest.main()
