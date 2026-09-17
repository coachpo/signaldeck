import { vi } from "vitest";

// Browsers omit crypto.randomUUID and crypto.subtle outside secure contexts,
// such as SignalDeck opened over plain HTTP from a trusted-network address.
export function stubInsecureContext() {
  const getRandomValues = crypto.getRandomValues.bind(crypto);
  vi.stubGlobal("crypto", { getRandomValues });
}
