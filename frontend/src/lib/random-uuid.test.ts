import { afterEach, expect, it, vi } from "vitest";
import { stubInsecureContext } from "@/test/insecure-context";
import { randomUUID } from "./random-uuid";

const version4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("uses the browser generator in a secure context", () => {
  const native = vi.spyOn(crypto, "randomUUID").mockReturnValue("6f1c1c3e-2b1a-4c55-9d0e-0f4b1d2c3a4b");
  expect(randomUUID()).toBe("6f1c1c3e-2b1a-4c55-9d0e-0f4b1d2c3a4b");
  expect(native).toHaveBeenCalledOnce();
});

it("creates distinct version 4 identities over plain HTTP", () => {
  stubInsecureContext();
  const values = Array.from({ length: 64 }, () => randomUUID());
  for (const value of values) expect(value).toMatch(version4);
  expect(new Set(values).size).toBe(values.length);
});

it("sets the version and variant bits over the random bytes", () => {
  vi.stubGlobal("crypto", { getRandomValues: (bytes: Uint8Array) => bytes.fill(0xff) });
  expect(randomUUID()).toBe("ffffffff-ffff-4fff-bfff-ffffffffffff");
});
