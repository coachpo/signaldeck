"""Serve the presentation bundle packaged with each independent plugin artifact."""

from pathlib import Path

from fastapi.staticfiles import StaticFiles


def mount_shared_ui(app):
    # API-only development does not need the optional browser build on disk.
    app.mount(
        "/ui",
        StaticFiles(directory=Path(__file__).with_suffix(""), check_dir=False),
        name="shared-ui",
    )
