import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ApiRequestError } from "@/lib/api-client";
import { RequestError } from "./feedback";

it("offers conflict recovery without exposing transport details", () => {
  const retry = vi.fn();
  render(<RequestError retry={retry} error={new ApiRequestError({
    code: "draft_conflict", status: 409,
    message: "Draft 69fb internal database conflict",
    details: [{ path: "/private/runtime/state.json", revision: 17 }],
  })} />);
  expect(screen.getByText("草稿已在其他窗口更新")).toBeVisible();
  expect(screen.getByText(/可以另存一份/)).toBeVisible();
  expect(document.body).not.toHaveTextContent(/69fb|draft_conflict|private\/runtime|revision/);
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  expect(retry).toHaveBeenCalledOnce();
});

it("keeps uncertain operations cautious without revealing a provider exception", () => {
  render(<RequestError error={new Error("Traceback: ConnectionResetError /srv/provider.py")} />);
  expect(screen.getByText("暂时未能完成操作")).toBeVisible();
  expect(screen.getByText(/避免重复操作/)).toBeVisible();
  expect(document.body).not.toHaveTextContent(/Traceback|ConnectionResetError|provider.py/);
});
