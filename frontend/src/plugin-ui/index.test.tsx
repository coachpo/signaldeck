import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { confirmDelete, renderMarkdown } from "./index";

afterEach(() => { document.body.replaceChildren(); });

describe("independent plugin presentation", () => {
  it("renders platform Markdown structures without executing HTML or fetching images", () => {
    const target = document.createElement("article");
    document.body.append(target);
    act(() => renderMarkdown(target, "# Report\n\n**Strong**\n\n1. One\n2. Two\n\n| Name | Value |\n|---|---|\n| A | B |\n\n```js\nconst value = 1\n```\n\n![private](https://example.com/pixel)\n\n[Unsafe](javascript:alert(1))\n\n<script>alert(1)</script>"));
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(target.querySelector("strong")).toHaveTextContent("Strong");
    expect(screen.getByRole("region", { name: "表格" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByLabelText("代码块")).toHaveAttribute("tabindex", "0");
    expect(target.querySelector("img, script, a")).toBeNull();
    act(() => renderMarkdown(target, "Updated"));
    expect(target).toHaveTextContent("Updated");
    expect(target.querySelector("table")).toBeNull();
  });

  it("cancels without confirmation and returns focus to the invoking control", async () => {
    const trigger = document.createElement("button");
    document.body.append(trigger);
    trigger.focus();
    let result!: Promise<boolean>;
    act(() => { result = confirmDelete({ title: "删除报告", description: "删除后无法恢复。" }); });
    expect(await screen.findByRole("alertdialog")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(await result).toBe(false);
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(trigger).toHaveFocus();
  });

  it("resolves a confirmed deletion exactly once", async () => {
    const confirm = vi.fn();
    let result!: Promise<boolean>;
    act(() => { result = confirmDelete({ title: "删除格式", description: "删除后无法恢复。" }); });
    void result.then(confirm);
    fireEvent.click(await screen.findByRole("button", { name: "删除" }));
    expect(await result).toBe(true);
    expect(confirm).toHaveBeenCalledExactlyOnceWith(true);
  });
});
