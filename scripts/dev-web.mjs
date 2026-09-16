import { spawn } from "node:child_process";
import { createHmac, randomBytes, randomUUID } from "node:crypto";
import { mkdir, open, readFile, rm, rmdir } from "node:fs/promises";
import { homedir } from "node:os";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import { createServer } from "vite";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const contract = JSON.parse(await readFile(resolve(root, "services/core/src/livingworld/domain/api_contract.json"), "utf8"));
const base = resolve(process.env.LOCALAPPDATA || resolve(homedir(), ".local/share"), "LivingWorld/development");
const nonce = randomUUID();
const secret = randomBytes(32).toString("hex");
const runtime = resolve(base, "runtime", nonce);
await mkdir(runtime, { recursive: true });
const bootstrap = resolve(runtime, "bootstrap.json");
const file = await open(bootstrap, "wx", 0o600);
await file.writeFile(JSON.stringify({
  bootstrap_secret: secret, instance_nonce: nonce,
  protocol_min: contract.api_protocol, protocol_max: contract.api_protocol,
  data_dir: resolve(base, "data"), log_dir: resolve(base, "logs"),
  allowed_origins: ["http://127.0.0.1:5173"],
}));
await file.close();
const python = resolve(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const child = spawn(python, ["-m", "livingworld.bootstrap", "--bootstrap-path", bootstrap], {
  cwd: root, stdio: ["ignore", "pipe", "pipe"], windowsHide: true,
});
child.stdout.pipe(process.stdout);
// Never forward raw exception or interpreter output.
child.stderr.resume();
let spawnError = false;
child.on("error", () => { spawnError = true; });
let connection;
let vite;
let stopping = false;
async function cleanup() {
  if (stopping) return;
  stopping = true;
  await vite?.close();
  if (connection && child.exitCode === null && !spawnError) {
    try {
      await fetch(`${connection.endpoint}/system/shutdown`, { method: "POST",
        headers: { Authorization: `Bearer ${connection.token}`, "X-Request-Id": randomUUID() },
        signal: AbortSignal.timeout(2_000),
      });
    } catch { /* The bounded termination path below still runs. */ }
  }
  const deadline = Date.now() + 6_000;
  while (child.exitCode === null && !spawnError && Date.now() < deadline) await delay(40);
  if (child.exitCode === null && !spawnError) {
    if (process.platform === "win32") {
      const terminate = spawn(resolve(process.env.SystemRoot, "System32/taskkill.exe"),
        ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true, stdio: "ignore" });
      await new Promise((done, reject) => { terminate.once("exit", done); terminate.once("error", reject); });
    } else child.kill();
    if (child.exitCode === null)
    await new Promise((done) => child.once("exit", done));
  }
  for (const name of ["bootstrap.json", "ready.json", "ready.tmp"]) await rm(resolve(runtime, name), { force: true });
  await rmdir(runtime);
}
process.once("SIGINT", () => { void cleanup().then(() => process.exit(0)); });
process.once("SIGTERM", () => { void cleanup().then(() => process.exit(0)); });
// Test harnesses request the same graceful path without Windows console signals.
if (process.argv.includes("--smoke")) process.stdin.on("data", (data) => {
  if (data.toString().trim() === "stop") void cleanup().then(() => process.exit(0));
});
try {
  const deadline = Date.now() + 15_000;
  let ready;
  while (!ready) {
    if (spawnError || child.exitCode !== null || Date.now() > deadline) throw new Error("core_start_failed");
    try { ready = JSON.parse(await readFile(resolve(runtime, "ready.json"), "utf8")); }
    catch { await delay(40); }
  }
  if (ready.instance_nonce !== nonce || (ready.pid !== child.pid && ready.launcher_pid !== child.pid) || ready.api_protocol !== contract.api_protocol) {
    throw new Error("ready_contract_failed");
  }
  const url = new URL(ready.endpoint);
  if (url.protocol !== "http:" || url.hostname !== contract.loopback_host || !url.port) throw new Error("loopback_required");
  const token = createHmac("sha256", secret).update(`${contract.session_derivation}:${nonce}:${ready.generation}`).digest("hex");
  connection = { endpoint: ready.endpoint, token, generation: ready.generation };
  process.env.LW_CORE_ENDPOINT = connection.endpoint;
  process.env.LW_CORE_TOKEN = connection.token;
  process.env.LW_CORE_GENERATION = connection.generation;
  vite = await createServer({ root: resolve(root, "apps/web"), configFile: resolve(root, "apps/web/vite.config.ts"),
    server: { host: "127.0.0.1", port: 5173, strictPort: true } });
  await vite.listen();
  vite.printUrls();
  child.once("exit", () => { if (!stopping) void cleanup().then(() => process.exit(1)); });
} catch {
  console.error("development_runtime_failed");
  await cleanup();
  process.exitCode = 1;
}
