import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(__dirname, "..");
const apiBaseUrl = process.env.VITE_API_BASE_URL ?? `http://127.0.0.1:${process.env.SIGNALDECK_E2E_BACKEND_PORT ?? "8001"}/api`;
const frontendPort = process.env.SIGNALDECK_E2E_FRONTEND_PORT ?? "4173";
const buildDirectory = process.env.SIGNALDECK_E2E_BUILD_DIR ?? "dist";

function runBuild() {
  return new Promise((resolveBuild, rejectBuild) => {
    const build = spawn("npx", ["vite", "build", "--outDir", buildDirectory], {
      cwd: frontendDir,
      env: {
        ...process.env,
        VITE_API_BASE_URL: apiBaseUrl,
      },
      stdio: "inherit",
    });

    build.on("error", rejectBuild);
    build.on("exit", (code) => {
      if (code === 0) {
        resolveBuild();
        return;
      }

      rejectBuild(
        new Error(`vite build failed with exit code ${code ?? "unknown"}`),
      );
    });
  });
}

async function main() {
  await runBuild();

  const child = spawn(
    "npx",
    [
      "vite",
      "preview",
      "--outDir",
      buildDirectory,
      "--port",
      frontendPort,
      "--strictPort",
      "--host",
      "127.0.0.1",
    ],
    {
      cwd: frontendDir,
      env: {
        ...process.env,
        VITE_API_BASE_URL: apiBaseUrl,
      },
      stdio: "inherit",
    },
  );

  process.on("SIGTERM", () => child.kill());
  process.on("SIGINT", () => child.kill());
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
