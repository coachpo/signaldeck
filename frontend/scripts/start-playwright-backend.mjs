import { spawn, spawnSync } from "node:child_process";
import { dirname, resolve, join } from "node:path";
import {
  existsSync,
  mkdtempSync,
  rmSync,
  chmodSync,
  readdirSync,
  writeFileSync,
  readFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { createConnection } from "node:net";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const backendDir = resolve(__dirname, "..", "..", "backend");
const backendPort = process.env.SIGNALDECK_E2E_BACKEND_PORT ?? "8001";
const fakeProviderPort = process.env.SIGNALDECK_FAKE_PROVIDER_PORT ?? "18081";
const fakeProviderBaseUrl =
  process.env.SIGNALDECK_FAKE_PROVIDER_BASE_URL ??
  `http://127.0.0.1:${fakeProviderPort}/v1`;
const children = new Set();
const expectedExits = new Set();
const controlFile = process.env.SIGNALDECK_E2E_CONTROL_FILE;
let controlFileOwned = false;
let controlTimer;
let controlState;

const runtimeDirectory = mkdtempSync(join(tmpdir(), "signaldeck-e2e-"));
const temporalCli =
  process.env.TEMPORAL_CLI ??
  (existsSync("/tmp/sd-temporal-bin/temporal")
    ? "/tmp/sd-temporal-bin/temporal"
    : "temporal");
const temporalPort = process.env.SIGNALDECK_E2E_TEMPORAL_PORT ?? "17233";
const e2eDatabaseName = `signaldeck_e2e_${process.pid}_${Date.now()}`;
let backendEnv = process.env;
let pythonExecutable;
const ownedDatabases = new Set();
let shuttingDown = false;

const databaseManagerScript = String.raw`
import os
import re
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import DEFAULT_DATABASE_URL


def quote_identifier(identifier):
    return '"' + identifier.replace('"', '""') + '"'


command, database_name = sys.argv[1], sys.argv[2]
if not re.fullmatch(r"signaldeck_e2e_[A-Za-z0-9_]+", database_name):
    raise RuntimeError(f"Refusing to manage non-e2e database: {database_name}")

base_database_url = make_url(os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL)
if base_database_url.get_backend_name() not in {"postgresql", "postgres"}:
    raise RuntimeError("Playwright e2e requires a PostgreSQL DATABASE_URL.")

admin_database_url = base_database_url.set(database="postgres")
target_database_url = base_database_url.set(database=database_name)
engine = create_engine(admin_database_url, isolation_level="AUTOCOMMIT", future=True)
try:
    with engine.connect() as connection:
        if command == "create":
            connection.execute(text(f"CREATE DATABASE {quote_identifier(database_name)}"))
            print(target_database_url.render_as_string(hide_password=False))
        elif command == "drop":
            connection.execute(
                text(f"DROP DATABASE IF EXISTS {quote_identifier(database_name)} WITH (FORCE)")
            )
        else:
            raise RuntimeError(f"Unsupported database command: {command}")
finally:
    engine.dispose()
`;

function exitCodeFor(code, signal) {
  if (typeof code === "number") {
    return code;
  }
  return signal ? 1 : 0;
}

function runDatabaseManager(command, databaseName = e2eDatabaseName) {
  const result = spawnSync(
    "uv",
    [
      "run",
      "--frozen",
      "python",
      "-c",
      databaseManagerScript,
      command,
      databaseName,
    ],
    {
      cwd: backendDir,
      env: process.env,
      encoding: "utf8",
    },
  );
  if (result.status !== 0) {
    throw new Error(
      `Failed to ${command} Playwright e2e database.\n${result.stderr || result.stdout}`,
    );
  }
  return result.stdout.trim();
}

function createE2eDatabase() {
  // E2E owns a disposable DB so stale local rows cannot leak into Playwright.
  const databaseUrl = runDatabaseManager("create");
  ownedDatabases.add(e2eDatabaseName);
  return databaseUrl;
}

function dropE2eDatabase() {
  for (const databaseName of ownedDatabases) {
    try {
      runDatabaseManager("drop", databaseName);
      ownedDatabases.delete(databaseName);
    } catch (error) {
      console.warn(error);
    }
  }
}

function unlockOwnedDirectories(path) {
  chmodSync(path, 0o700);
  for (const entry of readdirSync(path, { withFileTypes: true }))
    if (entry.isDirectory() && !entry.isSymbolicLink())
      unlockOwnedDirectories(join(path, entry.name));
}

async function stopAll(exitCode = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
  }
  const deadline = Date.now() + 10000;
  while (
    [...children].some(
      (child) => child.exitCode === null && child.signalCode === null,
    ) &&
    Date.now() < deadline
  )
    await delay(100);
  for (const child of children)
    if (child.exitCode === null && child.signalCode === null)
      try {
        process.kill(-child.pid, "SIGKILL");
      } catch (error) {
        if (error.code !== "ESRCH") throw error;
      }
  clearInterval(controlTimer);
  if (controlFileOwned) {
    rmSync(controlFile, { force: true });
    rmSync(`${controlFile}.request`, { force: true });
  }
  dropE2eDatabase();
  unlockOwnedDirectories(runtimeDirectory);
  rmSync(runtimeDirectory, {
    recursive: true,
    force: true,
    maxRetries: 10,
    retryDelay: 200,
  });
  process.exit(exitCode);
}

function spawnProcess(label, command, args, env = backendEnv) {
  const child = spawn(command, args, {
    cwd: backendDir,
    env,
    stdio: "inherit",
    detached: true,
  });
  children.add(child);
  child.on("error", (error) => {
    console.error(`${label} failed to start: ${error.message}`);
    void stopAll(1);
  });
  child.on("exit", (code, signal) => {
    children.delete(child);
    if (expectedExits.delete(child)) {
      if (controlFileOwned && !shuttingDown) {
        controlState = { ...controlState, status: "temporal_stopped" };
        writeFileSync(controlFile, JSON.stringify(controlState));
      }
      return;
    }
    if (shuttingDown) return;
    console.error(
      `${label} exited with code ${code ?? "unknown"} signal ${signal ?? "none"}`,
    );
    void stopAll(exitCodeFor(code, signal));
  });
  return child;
}
function spawnOwned(label, args) {
  if (args[0] !== "run" || args[1] !== "--frozen" || args[2] !== "python")
    throw new Error("Owned services require the verified Python interpreter");
  return spawnProcess(label, pythonExecutable, args.slice(3));
}
async function waitForPort(port, child) {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null || child.signalCode !== null)
      throw new Error(`Owned service exited before port ${port} became ready`);
    const ready = await new Promise((resolvePort) => {
      const socket = createConnection({
        host: "127.0.0.1",
        port: Number(port),
      });
      socket.once("connect", () => {
        socket.destroy();
        resolvePort(true);
      });
      socket.once("error", () => resolvePort(false));
      socket.setTimeout(500, () => {
        socket.destroy();
        resolvePort(false);
      });
    });
    if (ready) return;
    await delay(100);
  }
  throw new Error(`Owned service did not listen on port ${port}`);
}

async function main() {
  const pluginUi = spawnSync("pnpm", ["build:plugin-ui"], {
    cwd: resolve(__dirname, ".."),
    env: process.env,
    stdio: "inherit",
  });
  if (pluginUi.error) throw pluginUi.error;
  if (pluginUi.status !== 0) throw new Error("Plugin UI build failed");
  const e2eDatabaseUrl = createE2eDatabase();
  const interpreter = spawnSync(
    "uv",
    ["run", "--frozen", "python", "-c", "import sys; print(sys.executable)"],
    { cwd: backendDir, env: process.env, encoding: "utf8" },
  );
  if (interpreter.status !== 0)
    throw new Error("Cannot resolve the locked Python environment");
  pythonExecutable = interpreter.stdout.trim();
  const presetsPath = join(runtimeDirectory, "connection-presets.json");
  writeFileSync(presetsPath, JSON.stringify({items: [
    {id:"local-model", name:"本地受控研究服务", description:"仅用于隔离测试，不访问真实模型供应商。", resourceId:"research-model", kind:"model", config:{name:"Controlled local research",baseUrl:fakeProviderBaseUrl,modelId:"fake-e2e-oracle-tools",apiStyle:"chat_completions"}, credentialFields:[{key:"apiKey",label:"本地测试密钥",required:true}]},
    {id:"local-notes", name:"本地笔记保存位置", description:"本次测试独立笔记库",resourceId:"notes-workspace",kind:"tool",config:{pluginId:"example/notes",scope:{collection:"research"}},credentialFields:[]},
    {id:"local-finance",name:"本地受控行情",description:"固定测试行情，不代表真实市场",resourceId:"finance-market-data",kind:"tool",config:{pluginId:"signaldeck/finance",scope:{allowedSymbols:["MSFT","AAPL"]}},credentialFields:[]},
  ]}));
  backendEnv = {
    ...process.env,
    DATABASE_URL: e2eDatabaseUrl,
    SIGNALDECK_WORKFLOW_DATA_DIR: resolve(backendDir, "..", "demo"),
    SIGNALDECK_CONNECTION_PRESETS_FILE: presetsPath,
    OPENAI_API_KEY: "sk-e2e-fake-provider",
    OPENAI_BASE_URL: fakeProviderBaseUrl,
    TEMPORAL_ADDRESS: `127.0.0.1:${temporalPort}`,
    SIGNALDECK_ARTIFACT_DIR: join(runtimeDirectory, "artifacts"),
    SIGNALDECK_CORE_ARTIFACT_DIR: join(runtimeDirectory, "core"),
    SIGNALDECK_CORE_ENV_DIR: join(runtimeDirectory, "environments"),
    SIGNALDECK_CORE_PYTHON_VERSION: "3.13.13",
    SIGNALDECK_RUNTIME_MODE: "test",
    LOGFIRE_TOKEN: "",
    LOGFIRE_API_KEY: "",
    LOGFIRE_CREDENTIALS_DIR: join(runtimeDirectory, "logfire"),
    LOGFIRE_CONFIG_DIR: join(runtimeDirectory, "logfire"),
    OTEL_EXPORTER_OTLP_ENDPOINT: "",
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: "",
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: "",
    OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: "",
    SIGNALDECK_API_TOKEN: "",
    CORS_ALLOWED_ORIGINS: [
      `http://127.0.0.1:${process.env.SIGNALDECK_E2E_FRONTEND_PORT ?? "4173"}`,
      `http://localhost:${process.env.SIGNALDECK_E2E_FRONTEND_PORT ?? "4173"}`,
    ].join(","),
    SIGNALDECK_FAKE_PROVIDER_BASE_URL: fakeProviderBaseUrl,
    SIGNALDECK_FAKE_PROVIDER_PORT: fakeProviderPort,
  };
  const cliVersion = spawnSync(temporalCli, ["--version"], {
    encoding: "utf8",
  });
  if (
    cliVersion.status !== 0 ||
    !/^temporal version 1\.8\.3 \(Server 1\.31\.2[,)]/m.test(cliVersion.stdout)
  )
    throw new Error(
      "E2E requires Temporal CLI 1.8.3 (Server 1.31.2). Set TEMPORAL_CLI to its executable path.",
    );
  const temporal = spawnProcess("Temporal dev server", temporalCli, [
    "server",
    "start-dev",
    "--ip",
    "127.0.0.1",
    "--port",
    temporalPort,
    "--headless",
    "--db-filename",
    join(runtimeDirectory, "temporal.sqlite"),
    "--log-level",
    "warn",
  ]);
  await waitForPort(temporalPort, temporal);
  // Only the explicitly isolated fault configuration can stop this owned server.
  // Tests submit a nonce-bound file request; they never signal a discovered PID.
  if (controlFile && process.env.SIGNALDECK_E2E_ALLOW_ENGINE_STOP === "1") {
    controlState = {
      nonce: crypto.randomUUID(),
      requestPath: `${controlFile}.request`,
      temporalPid: temporal.pid,
      status: "running",
    };
    writeFileSync(controlFile, JSON.stringify(controlState), { flag: "wx", mode: 0o600 });
    controlFileOwned = true;
    controlTimer = setInterval(() => {
      if (!existsSync(controlState.requestPath) || controlState.status !== "running") return;
      let request;
      try { request = JSON.parse(readFileSync(controlState.requestPath, "utf8")); }
      catch { return; }
      if (request.nonce !== controlState.nonce || request.action !== "stop_temporal") return;
      controlState.status = "stopping_temporal";
      expectedExits.add(temporal);
      process.kill(-temporal.pid, "SIGTERM");
    }, 100);
  }

  const provider = spawnOwned("fake OpenAI-compatible provider", [
    "run",
    "--frozen",
    "python",
    "tests/fake_openai_provider.py",
    "--host",
    "127.0.0.1",
    "--port",
    fakeProviderPort,
  ]);
  await waitForPort(fakeProviderPort, provider);
  for (const [kind, defaultPort] of [["notes", "18082"], ["finance", "18083"], ["oracle", "18084"]]) {
    const port = process.env[`SIGNALDECK_E2E_${kind.toUpperCase()}_PORT`] ?? defaultPort;
    const databaseName = `${e2eDatabaseName}_${kind}`;
    const databaseUrl = runDatabaseManager("create", databaseName);
    ownedDatabases.add(databaseName);
    const child = spawnProcess(`${kind} plugin`, pythonExecutable, [
      resolve(__dirname, "e2e-plugin.py"), kind, port,
    ], {
      ...backendEnv,
      PLUGIN_DATABASE_URL: databaseUrl,
      PLUGIN_ENDPOINT: `http://127.0.0.1:${port}/mcp/`,
      PLUGIN_PAGE_URL: `http://127.0.0.1:${port}/`,
      PYTHONDONTWRITEBYTECODE: "1",
    });
    await waitForPort(port, child);
  }
  spawnOwned("command dispatcher", [
    "run",
    "--frozen",
    "python",
    "-m",
    "app.workers.command_dispatcher",
  ]);
  spawnOwned("core artifact worker supervisor", [
    "run",
    "--frozen",
    "python",
    "-m",
    "app.workers.artifact_worker",
    "--serve",
    "--source",
    backendDir,
  ]);
  spawnOwned("backend", [
    "run",
    "--frozen",
    "python",
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    backendPort,
  ]);
}

process.on("SIGTERM", () => stopAll(0));
process.on("SIGINT", () => stopAll(0));

main().catch((error) => {
  console.error(error);
  stopAll(1);
});
