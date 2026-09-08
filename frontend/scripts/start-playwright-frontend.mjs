import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(__dirname, "..");
const apiBaseUrl = process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8001/api";

function runBuild() {
  return new Promise((resolveBuild, rejectBuild) => {
    const build = spawn("npx", ["vite", "build"], {
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
      "--port",
      "4173",
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
