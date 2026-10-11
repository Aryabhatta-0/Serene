// Readers for kernel payloads. Every surface validates what the kernel sends
// at the boundary and fails closed: a value that does not have the exact
// shape the kernel's Pydantic model allows is an error, never a guess.
//
// `wireReader(fail)` binds the readers to a surface's own error type, so a
// memory payload throws a memory error and a twin payload a twin error.

export type Json = Record<string, unknown>;

// serene.domain.base.ID_PREFIXES
const ENTITY_PREFIXES = new Set([
  "chd", "act", "src", "evt", "evd", "obs", "pat", "hyp",
  "inv", "exp", "trl", "out", "lrn", "mpt", "apr", "erq",
]);
const ID_RE = /^([a-z]{3})_[0-9a-f]{32}$/;
const TAG_RE = /^[a-z][a-z0-9_]{0,63}$/;
const SHA256_RE = /^[0-9a-f]{64}$/;
const GIT_SHA_RE = /^[0-9a-f]{40}$/;
// serene.domain.base.ReasonCode: an upper-case code, optionally ":" and detail.
const REASON_RE = /^[A-Z][A-Z0-9_]{0,63}(:[A-Za-z0-9_]{1,64})?$/;

export type Fail = (path: string, problem: string) => never;

export function wireReader(fail: Fail) {
  function object(value: unknown, path: string): Json {
    if (typeof value !== "object" || value === null || Array.isArray(value)) fail(path, "expected an object");
    return value as Json;
  }

  function array(value: unknown, path: string, max: number, min = 0): unknown[] {
    if (!Array.isArray(value)) fail(path, "expected a list");
    if (value.length < min || value.length > max) fail(path, `expected ${min} to ${max} items`);
    return value;
  }

  function text(value: unknown, path: string, max = 500): string {
    if (typeof value !== "string" || value.length < 1 || value.length > max) fail(path, "expected text");
    return value;
  }

  function id(value: unknown, path: string, prefix?: string): string {
    const match = typeof value === "string" ? ID_RE.exec(value) : null;
    if (!match || !ENTITY_PREFIXES.has(match[1]) || (prefix && match[1] !== prefix)) {
      fail(path, prefix ? `expected a ${prefix}_ id` : "expected an entity id");
    }
    return value as string;
  }

  function ids(value: unknown, path: string, max: number, prefix?: string, min = 0): string[] {
    return array(value, path, max, min).map((item, i) => id(item, `${path}[${i}]`, prefix));
  }

  function oneOf<T extends string>(value: unknown, allowed: readonly T[], path: string): T {
    if (!allowed.includes(value as T)) fail(path, `expected one of ${allowed.join(", ")}`);
    return value as T;
  }

  function tag(value: unknown, path: string): string {
    if (typeof value !== "string" || !TAG_RE.test(value)) fail(path, "expected a tag");
    return value;
  }

  function optional<T>(value: unknown, read: (v: unknown) => T): T | null {
    return value === null || value === undefined ? null : read(value);
  }

  function timestamp(value: unknown, path: string): string {
    if (typeof value !== "string" || Number.isNaN(Date.parse(value))) fail(path, "expected a timestamp");
    return value;
  }

  function integer(value: unknown, path: string, min: number, max: number): number {
    if (!Number.isInteger(value) || (value as number) < min || (value as number) > max) {
      fail(path, `expected a whole number from ${min} to ${max}`);
    }
    return value as number;
  }

  function bool(value: unknown, path: string): boolean {
    if (typeof value !== "boolean") fail(path, "expected true or false");
    return value;
  }

  function sha256(value: unknown, path: string): string {
    if (typeof value !== "string" || !SHA256_RE.test(value)) fail(path, "expected a sha256 digest");
    return value;
  }

  function gitSha(value: unknown, path: string): string {
    if (typeof value !== "string" || !GIT_SHA_RE.test(value)) fail(path, "expected a commit id");
    return value;
  }

  function reasons(value: unknown, path: string, max: number, min = 0): string[] {
    return array(value, path, max, min).map((code, i) => {
      if (typeof code !== "string" || !REASON_RE.test(code)) fail(`${path}[${i}]`, "expected a reason code");
      return code;
    });
  }

  return { object, array, text, id, ids, oneOf, tag, optional, timestamp, integer, bool, sha256, gitSha, reasons };
}
