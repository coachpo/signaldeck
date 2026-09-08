import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { createWriteStream, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { expect, type APIRequestContext } from "@playwright/test";

export async function startHeldPlugin(request: APIRequestContext) {
  const listener = createServer();
  await new Promise<void>((done, reject) => { listener.once("error", reject); listener.listen(0, "127.0.0.1", done); });
  const address = listener.address();
  if (!address || typeof address === "string") throw new Error("Owned plugin port was not allocated");
  const port = address.port;
  await new Promise<void>((done) => listener.close(() => done()));
  const directory = mkdtempSync(join(tmpdir(), "signaldeck-held-e2e-"));
  const identity = crypto.randomUUID().slice(0, 8);
  const child = spawn("uv", ["run", "--frozen", "python", resolve("scripts/e2e-held-plugin.py"), directory, String(port), identity], {
    cwd: resolve("../backend"),
    env: {...process.env, PYTHONDONTWRITEBYTECODE:"1", LOGFIRE_TOKEN:"", LOGFIRE_API_KEY:"", OTEL_EXPORTER_OTLP_ENDPOINT:""},
    detached: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const log = createWriteStream(join(directory,"plugin.log"));
  child.stdout.pipe(log, {end:false});
  child.stderr.pipe(log, {end:false});
  let launchError: Error | undefined;
  child.on("error", error => { launchError = error; });
  async function stop() {
    if (child.exitCode !== null || child.signalCode !== null) return;
    const exited = new Promise<void>(done => child.once("exit", () => done()));
    process.kill(-child.pid!, "SIGTERM");
    await exited;
  }
  async function dispose() {
    writeFileSync(join(directory,"release"), "");
    await stop();
    log.end();
    rmSync(directory,{recursive:true,force:true});
  }
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    await expect.poll(async () => {
      if (launchError) throw launchError;
      expect(child.exitCode).toBeNull();
      return (await request.get(`${baseUrl}/health`,{timeout:500}).catch(() => null))?.status();
    }, {timeout:20000}).toBe(200);
    const response = await request.get(`${baseUrl}/release`);
    expect(response.ok()).toBe(true);
    return {directory, baseUrl, binding:await response.json(), stop, dispose};
  } catch (error) { await dispose(); throw error; }
}
