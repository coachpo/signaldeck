"""Create a private, non-overwriting configuration for the application stack."""

import argparse
import os
import re
import secrets
from pathlib import Path

SECRET_KEYS = (
    "POSTGRES_PASSWORD",
    "CORE_DB_PASSWORD",
    "FINANCE_DB_PASSWORD",
    "NOTES_DB_PASSWORD",
    "TEMPORAL_DB_PASSWORD",
    "AGENT_PLATFORM_ENCRYPTION_KEY",
)


def plugin_tag(value):
    if not re.fullmatch(r"sha-[0-9a-f]{40}", value):
        raise argparse.ArgumentTypeError(
            "must be sha- followed by 40 lowercase hex digits"
        )
    return value


def app_image(value):
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._/-]*"
        r"(?::v[0-9]+\.[0-9]+\.[0-9]+(?:@sha256:[0-9a-f]{64})?|@sha256:[0-9a-f]{64})",
        value,
    ):
        raise argparse.ArgumentTypeError(
            "must pin a release as <image>:vX.Y.Z[@sha256:<digest>] "
            "or <image>@sha256:<digest>"
        )
    return value


def render(template, tag, image):
    replacements = {key: secrets.token_hex(32) for key in SECRET_KEYS}
    replacements.update(SIGNALDECK_PLUGIN_TAG=tag, SIGNALDECK_IMAGE=image)
    seen = set()
    lines = []
    for line in template.splitlines():
        key = line.partition("=")[0]
        if key in replacements:
            if key in seen:
                raise ValueError("Duplicate configuration key in environment template")
            seen.add(key)
            line = f"{key}={replacements[key]}"
        lines.append(line)
    if seen != replacements.keys():
        raise ValueError("Missing configuration key in environment template")
    return "\n".join(lines) + "\n"


def ensure_directory(path):
    if path.is_dir():
        return
    ensure_directory(path.parent)
    path.mkdir(mode=0o700, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-tag", required=True, type=plugin_tag)
    parser.add_argument("--app-image", required=True, type=app_image)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / ".config/signaldeck/production.env",
    )
    args = parser.parse_args()
    output = args.output.expanduser().absolute()
    try:
        template = Path(__file__).with_name("production.env.example").read_text()
        content = render(template, args.plugin_tag, args.app_image)
        ensure_directory(output.parent)
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
    except FileExistsError:
        parser.exit(1, "Configuration already exists; refusing to overwrite it.\n")
    except (OSError, ValueError):
        parser.exit(
            1, "Could not create configuration; check its template and output path.\n"
        )
    print(output)


if __name__ == "__main__":
    main()
