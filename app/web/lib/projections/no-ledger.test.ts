import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

// Static check (Issue #33): the web app's view model is projection state, never
// the immutable event ledger. No source file may name the ledger table or a
// ledger reader, and the only Serene table any file queries is projection_state,
// apart from the one guardian-registry lookup that lists a signed-in parent's
// children (Issue #87), which is allowed in lib/auth/backend.ts alone.

const ROOT = process.cwd(); // vitest runs from app/web
const SCANNED = ["app", "components", "lib", "e2e"];
const SELF = ["lib", "projections", "no-ledger.test.ts"].join(sep);

// Built from parts so this file does not trip its own check.
const LEDGER = [
  ["domain", "events"].join("_"),
  ["get", "events", "for", "child"].join("_"),
  ["read", "stream"].join("_"),
  ["replay", "events"].join("_"),
  ["event", "ledger"].join("_"),
  ["Event", "Ledger"].join(""),
];

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(ts|tsx|mjs|js)$/.test(name) ? [path] : [];
  });
}

const files = SCANNED.flatMap((dir) => sources(join(ROOT, dir))).filter((f) => relative(ROOT, f) !== SELF);

describe("the web app reads no ledger", () => {
  it("scans the app's sources", () => {
    expect(JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8")).name).toBe("serene-web");
    expect(files.length).toBeGreaterThan(40);
    expect(files.some((f) => f.endsWith(join("lib", "projections", "supabase.ts")))).toBe(true);
  });

  it("names no ledger table or ledger reader", () => {
    const offenders = files.flatMap((file) => {
      const text = readFileSync(file, "utf8");
      return LEDGER.filter((needle) => text.includes(needle)).map((needle) => `${relative(ROOT, file)}: ${needle}`);
    });
    expect(offenders).toEqual([]);
  });

  it("queries no table but projection_state (and the guardian registry, from one file)", () => {
    const tables = files.flatMap((file) =>
      [...readFileSync(file, "utf8").matchAll(/\.from\(\s*["'`]([^"'`]+)["'`]\s*\)|table:\s*["'`]([^"'`]+)["'`]/g)].map(
        (m) => `${relative(ROOT, file)}: ${m[1] ?? m[2]}`,
      ),
    );
    expect(tables.length).toBeGreaterThan(0);
    const registry = `${join("lib", "auth", "backend.ts")}: child_guardians`;
    expect(tables).toContain(registry);
    expect(tables.filter((t) => !t.endsWith(": projection_state") && t !== registry)).toEqual([]);
  });
});
