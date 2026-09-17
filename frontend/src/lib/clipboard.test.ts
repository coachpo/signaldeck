import { afterEach, expect, it, vi } from "vitest";
import { copyText } from "./clipboard";

afterEach(() => {
  Reflect.deleteProperty(navigator, "clipboard");
  Reflect.deleteProperty(document, "execCommand");
  document.body.replaceChildren();
});

// Like a page opened over plain HTTP, jsdom has no navigator.clipboard. It has no execCommand
// either, so record the selection the copy command would take.
function stubCopyCommand(accepted: boolean) {
  const copied: string[] = [];
  const execCommand = vi.fn((command: string) => {
    const field = document.activeElement as HTMLTextAreaElement;
    copied.push(`${command}:${field.value.slice(field.selectionStart, field.selectionEnd)}`);
    return accepted;
  });
  Object.defineProperty(document, "execCommand", { configurable: true, value: execCommand });
  return copied;
}

it("writes through the Clipboard API where the browser provides it", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const copied = stubCopyCommand(true);
  await copyText("# 正文");
  expect(writeText).toHaveBeenCalledWith("# 正文");
  expect(copied).toEqual([]);
});

it("copies the whole text from a temporary field during the click and restores focus", async () => {
  const button = document.body.appendChild(document.createElement("button"));
  button.focus();
  const copied = stubCopyCommand(true);
  const copying = copyText("# 正文\n\n\t原文 保持\n");
  // Browsers only run the copy command while the click that requested it is handled.
  expect(copied).toEqual(["copy:# 正文\n\n\t原文 保持\n"]);
  await copying;
  expect(document.querySelector("textarea")).toBeNull();
  expect(document.activeElement).toBe(button);
});

it("reports a copy the browser refused and removes the temporary field", async () => {
  const copied = stubCopyCommand(false);
  await expect(copyText("正文")).rejects.toThrow();
  expect(copied).toEqual(["copy:正文"]);
  expect(document.querySelector("textarea")).toBeNull();
});
