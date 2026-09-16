"""Verify the single-image deployment on a local Docker daemon using disposable owned storage."""

import argparse
import json
import os
import secrets
import socket
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx
from verify_target_stack import Check, notes_package, references

ROOT = Path(__file__).resolve().parents[1]
PASSWORDS = (
    "POSTGRES_PASSWORD",
    "CORE_DB_PASSWORD",
    "FINANCE_DB_PASSWORD",
    "NOTES_DB_PASSWORD",
    "TEMPORAL_DB_PASSWORD",
    "AGENT_PLATFORM_ENCRYPTION_KEY",
)
DATABASE_ISOLATION = r"""
set -eu
for role in core finance notes temporal; do
    case "$role" in
        core) export PGPASSWORD="$CORE_DB_PASSWORD" ;;
        finance) export PGPASSWORD="$FINANCE_DB_PASSWORD" ;;
        notes) export PGPASSWORD="$NOTES_DB_PASSWORD" ;;
        temporal) export PGPASSWORD="$TEMPORAL_DB_PASSWORD" ;;
    esac
    for database in core finance notes temporal temporal_visibility; do
        permitted=false
        if [ "$role" = "$database" ] || { [ "$role" = temporal ] && [ "$database" = temporal_visibility ]; }; then
            permitted=true
        fi
        if psql -h 127.0.0.1 -U "signaldeck_$role" -d "signaldeck_$database" \
            -v ON_ERROR_STOP=1 -Atc 'SELECT 1' >/dev/null 2>&1; then
            [ "$permitted" = true ] || exit 1
        else
            [ "$permitted" = false ] || exit 1
        fi
    done
done
"""


def verify(args):
    env = {key: os.environ[key] for key in ("PATH", "HOME")}
    env.update({name: secrets.token_hex(24) for name in PASSWORDS})
    plugins = {"notes": args.notes_image}
    if args.finance_image:
        plugins["finance"] = args.finance_image
        env["SIGNALDECK_FINANCE_IMAGE"] = args.finance_image
    if args.oracle_image:
        plugins["digital-oracle"] = args.oracle_image
        env["SIGNALDECK_ORACLE_IMAGE"] = args.oracle_image
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env.update(
        SIGNALDECK_IMAGE=args.app_image,
        SIGNALDECK_NOTES_IMAGE=args.notes_image,
        DATABASE_URL=f"postgresql+psycopg://signaldeck_core:{env['CORE_DB_PASSWORD']}@db:5432/signaldeck_core",
        FINANCE_DATABASE_URL=f"postgresql+psycopg://signaldeck_finance:{env['FINANCE_DB_PASSWORD']}@db:5432/signaldeck_finance",
        NOTES_DATABASE_URL=f"postgresql+psycopg://signaldeck_notes:{env['NOTES_DB_PASSWORD']}@db:5432/signaldeck_notes",
        TEMPORAL_ADDRESS="temporal:7233",
        SIGNALDECK_PLUGINS=",".join(plugins),
        APP_PORT=str(port),
    )

    def run(argv):
        result = subprocess.run(
            argv, cwd=ROOT, env=env, capture_output=True, text=True, check=False
        )
        if result.returncode:
            output = result.stdout + result.stderr
            for name in PASSWORDS:
                output = output.replace(env[name], "[REDACTED]")
            raise RuntimeError(output[-6000:])
        return result.stdout

    context = json.loads(run(["docker", "context", "inspect"]))[0]
    if not context["Endpoints"]["docker"]["Host"].startswith("unix://"):
        raise RuntimeError("Select a local Unix-socket Docker context for this test")
    for image in (args.app_image, *plugins.values()):
        run(["docker", "image", "inspect", image])
    project = "sd-deployment-check-" + uuid4().hex[:12]
    compose = [
        "docker",
        "compose",
        "--env-file",
        os.devnull,
        "-p",
        project,
        "-f",
        str(ROOT / "docker/compose.production.yml"),
    ]
    for profile in plugins:
        compose.extend(["--profile", profile])
    check = Check(f"http://127.0.0.1:{port}", f"http://127.0.0.1:{port}")
    completed = []
    try:
        run(compose + ["up", "-d"])
        run(compose + ["wait", "bootstrap"])
        run(compose + ["exec", "-T", "db", "sh", "-c", DATABASE_ISOLATION])
        completed.append(
            "fresh databases, four isolated roles, SQL schemas and default namespace"
        )
        assert len(check.request("/api/plugins")["items"]) == len(plugins)
        pages = check.request("/api/plugin-pages")
        mount_key = next(
            page["mountKey"] for page in pages if page["pluginId"] == "example/notes"
        )
        for page in pages:
            assert (
                check.client.get(
                    check.base + f"/_plugins/{page['mountKey']}/"
                ).status_code
                == 200
            )
        assert check.client.get(check.base + "/ready").json()["database"] == "ok"
        assert check.client.get(check.base + "/").status_code == 200
        assert (
            check.client.get(
                check.base + "/api/workflow-packages", headers={"Authorization": ""}
            ).status_code
            == 200
        )
        assert (
            check.client.get(
                check.base + f"/_plugins/{mount_key}/api/collections"
            ).status_code
            == 200
        )
        package = notes_package("capy")
        check.request(
            "/api/workflow-packages", {"manifestSource": json.dumps(package)}, "POST"
        )
        content = "Isolated persistent Temporal deployment. " * 2400
        result = check.launch(
            package["metadata"]["key"],
            "capture",
            {
                "title": "Local deployment validation",
                "text": content,
            },
            "capture-" + uuid4().hex,
        )
        assert check.value(result["output"])["text"] == content
        refs = references(result)
        assert refs
        completed.append(
            "public plugin bootstrap, gateway, durable Notes execution and large artifacts"
        )
        schedule = check.request(
            "/api/schedules",
            {
                "name": "Local persistent schedule",
                "packageKey": package["metadata"]["key"],
                "workflowKey": "capture",
                "parameters": {"title": "Scheduled", "text": "Local test"},
                "cron": "0 0 1 1 *",
                "timeZone": "UTC",
                "overlapPolicy": "skip",
                "catchupWindowSeconds": 60,
                "paused": True,
            },
            "POST",
        )
        logs = run(compose + ["logs", "--no-color"])
        assert not any(
            env[name] in logs for name in PASSWORDS
        ), "Startup secret leaked to logs"
        run(compose + ["stop", "--timeout", "30", "app", "dispatcher", "worker"])
        for role in ("app", "dispatcher", "worker"):
            container = run(compose + ["ps", "--all", "--quiet", role]).strip()
            state = json.loads(run(["docker", "inspect", container]))[0]["State"]
            assert state["ExitCode"] == 0, f"{role} did not stop gracefully"
        completed.append(
            "application, dispatcher and pinned workers stop gracefully on SIGTERM"
        )
        run(compose + ["down", "--timeout", "30"])
        run(compose + ["up", "-d"])
        run(compose + ["wait", "bootstrap"])
        assert check.request("/api/runs/" + result["id"])["status"] == "succeeded"
        for ref in refs:
            check.artifact(ref)
        history = run(
            compose
            + [
                "run",
                "--rm",
                "--no-deps",
                "--entrypoint",
                "temporal",
                "temporal-namespace",
                "workflow",
                "list",
                "--output",
                "json",
            ]
        )
        assert result["id"] in history
        completed.append(
            "container recreation preserves PostgreSQL, Temporal history, Core closures and artifacts"
        )
        trigger = {"triggerId": "trigger-" + uuid4().hex}
        for _ in range(2):
            check.request(f"/api/schedules/{schedule['id']}/trigger", trigger, "POST")
        deadline = time.monotonic() + 90
        scheduled = []
        while time.monotonic() < deadline:
            scheduled = [
                r
                for r in check.request("/api/runs")["items"]
                if r["origin"].get("scheduleId") == schedule["id"]
            ]
            if scheduled:
                break
            time.sleep(0.5)
        assert len(scheduled) == 1
        check.wait_run(scheduled[0]["id"])
        completed.append(
            "retained schedule executes after restart; duplicate trigger creates one Run"
        )
        logs = run(compose + ["logs", "--no-color"])
        assert not any(
            env[name] in logs for name in PASSWORDS
        ), "Runtime secret leaked to logs"
        run(compose + ["stop", "worker", "dispatcher", "temporal", *plugins])
        run(compose + ["restart", "app"])
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if (
                    check.client.get(check.base + "/ready", timeout=3).status_code
                    == 200
                ):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        assert check.request("/api/runs/" + result["id"])["status"] == "succeeded"
        for ref in refs:
            check.artifact(ref)
        completed.append(
            "cold-start offline history remains readable; startup/runtime secrets absent from logs"
        )
    except Exception:
        for service in (
            "db",
            "temporal-schema",
            "temporal",
            "temporal-namespace",
            "worker",
            "app",
            "plugin-mounts",
            "bootstrap",
        ):
            logs = run(compose + ["logs", "--tail", "15", "--no-color", service])
            for name in PASSWORDS:
                logs = logs.replace(env[name], "[REDACTED]")
            print(logs[-4000:])
        raise
    finally:
        check.client.close()
        run(compose + ["down", "--volumes", "--timeout", "30", "--remove-orphans"])
    for item in completed:
        print("PASS:", item)
    print("Removed only owned test containers, network and volumes:", project)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-image", default="signaldeck:local")
    parser.add_argument("--notes-image", default="signaldeck-notes:1.3.0")
    parser.add_argument(
        "--finance-image",
        help="Also verify Finance startup, registration and page mount",
    )
    parser.add_argument(
        "--oracle-image",
        help="Also verify Oracle startup and registration without provider calls",
    )
    args = parser.parse_args()
    verify(args)


if __name__ == "__main__":
    main()
