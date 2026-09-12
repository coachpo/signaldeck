import { render } from "@testing-library/react";
import { expect, it } from "vitest";
import { useUnsavedWork } from "./use-unsaved-work";

function Editor({ changed }: { changed: boolean }) {
  useUnsavedWork(changed);
  return null;
}

it("protects unsaved edits from refresh and releases protection after saving", () => {
  const view = render(<Editor changed />);
  const unsafe = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(unsafe);
  expect(unsafe.defaultPrevented).toBe(true);
  view.rerender(<Editor changed={false} />);
  const saved = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(saved);
  expect(saved.defaultPrevented).toBe(false);
});
