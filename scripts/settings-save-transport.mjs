// Test-only transport: real browser Request serialization -> stdin -> ASGI -> temporary SQLite.
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createInterface } from "node:readline";
import { isAbsolute, join, relative, resolve } from "node:path";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { File } from "node:buffer";

export function syntheticCardFile(document) {
  return new File([JSON.stringify(document)], "synthetic-player-card.json", { type: "application/json" });
}

export async function startSettingsBridge() {
  const parent = resolve(process.env.DREAMTALK_SAVE_CHECK_ROOT || tmpdir());
  const working = await mkdtemp(join(parent, "settings-save-transport-"));
  const within = relative(parent, resolve(working));
  if (!within || within.startsWith("..") || isAbsolute(within)) throw new Error("Invalid isolated directory");
  const environment = { ...process.env, DREAMTALK_SAVE_CHECK_ROOT: working, HF_HUB_OFFLINE: "1", TRANSFORMERS_OFFLINE: "1", PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1" };
  for (const [key, name] of Object.entries({ APPDATA: "roaming", LOCALAPPDATA: "local", USERPROFILE: "home", HOME: "home", HF_HOME: "hf", XDG_CACHE_HOME: "cache", TEMP: "tmp", TMP: "tmp", LIVINGWORLD_DATA_DIR: "data", LIVINGWORLD_BACKUP_DIR: "backups" })) {
    environment[key] = join(working, name);
    await mkdir(environment[key], { recursive: true });
  }
  const python = resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  const child = spawn(python, ["tests/settings_save_bridge.py"], {
    cwd: resolve("."), env: environment,
    stdio: "pipe",
  });
  let errors = "", world, ordinal = 0;
  const pending = new Map(), requests = [];
  child.stderr.on("data", chunk => { errors += String(chunk); });
  await new Promise((ready, reject) => {
    const lines = createInterface({ input: child.stdout });
    lines.on("line", line => {
      const reply = JSON.parse(line);
      if (reply.ready) { world = reply.world_id; ready(); return; }
      pending.get(reply.id)?.resolve(reply); pending.delete(reply.id);
    });
    child.on("error", reject);
    child.on("exit", code => {
      const error = new Error(`Isolated settings bridge exited: ${code}\n${errors}`);
      reject(error);
      pending.forEach(value => value.reject(error)); pending.clear(); lines.close();
    });
  });
  const fetcher = async (input, init) => {
    const request = new Request(input, init);
    requests.push(request.clone());
    const id = ++ordinal, body = await request.text();
    const response = await new Promise((resolveReply, reject) => {
      pending.set(id, { resolve: resolveReply, reject });
      const url = new URL(request.url);
      child.stdin.write(JSON.stringify({ id, method: request.method, path: url.pathname + url.search, headers: Object.fromEntries(request.headers.entries()), body }) + "\n");
    });
    return new Response(response.body, { status: response.status, headers: response.headers });
  };
  const close = async () => {
    if (child.exitCode === null) {
      const exited = once(child, "exit");
      child.stdin.end();
      await exited;
    }
    // The absolute cleanup target is the newly created child of our chosen temp parent.
    if (resolve(working) !== join(parent, within)) throw new Error("Invalid cleanup directory");
    await rm(working, { recursive: true, force: true });
  };
  return { world, requests, fetcher, close };
}
