import "server-only";
import { execFile } from "node:child_process";
import { resolve } from "node:path";
import { promisify } from "node:util";
import { parseDemoState } from "./model";

const run = promisify(execFile);

export async function readDemoState() {
  if (process.env.SERENE_DEMO_MODE !== "1") throw new Error("Demo mode is disabled");
  // Fixed local script and artifact; never accept a path, command or child id from a request.
  const { stdout } = await run("uv", ["run", "--no-sync", "python", "scripts/maya_web_state.py"], {
    cwd: resolve(process.cwd(), "../.."),
    timeout: 30_000,
    maxBuffer: 4 * 1024 * 1024,
    windowsHide: true,
  });
  const payload: unknown = JSON.parse(stdout);
  parseDemoState(payload);
  return payload;
}
