import { describe, expect, it } from "vitest";
import { forgetChild, recallChild, rememberChild } from "./selection";

const USER = "00000000-0000-0000-0000-000000000001";
const OTHER_USER = "00000000-0000-0000-0000-000000000002";
const A = `chd_${"a".repeat(32)}`;
const B = `chd_${"b".repeat(32)}`;
const C = `chd_${"c".repeat(32)}`;

function memory() {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
    data,
  };
}

describe("the remembered child", () => {
  it("is restored for the same user when RLS still lists it", () => {
    const store = memory();
    rememberChild(store, USER, B);
    expect(recallChild(store, USER, [A, B])).toBe(B);
  });

  it("is never restored for another user, or when it is no longer listed", () => {
    const store = memory();
    rememberChild(store, USER, C);
    expect(recallChild(store, OTHER_USER, [A, C])).toBe(A);
    expect(recallChild(store, USER, [A, B])).toBe(A);
  });

  it("falls back to the first listed child, or none", () => {
    expect(recallChild(memory(), USER, [A, B])).toBe(A);
    expect(recallChild(memory(), USER, [])).toBeNull();
    expect(recallChild(null, USER, [B])).toBe(B);
  });

  it("ignores a tampered value and can be forgotten", () => {
    const store = memory();
    store.setItem("serene.selected-child", "{not json");
    expect(recallChild(store, USER, [A, B])).toBe(A);
    store.setItem("serene.selected-child", JSON.stringify({ userId: USER, childId: 7 }));
    expect(recallChild(store, USER, [A, B])).toBe(A);
    rememberChild(store, USER, B);
    forgetChild(store);
    expect(store.data.size).toBe(0);
  });
});
