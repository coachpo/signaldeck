import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/components/theme-provider";
import { router } from "@/routes";
function renderRoute(path: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        headers: { "content-type": "application/json" },
      }),
    ),
  );
  return render(
    <ThemeProvider>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <RouterProvider
          router={createMemoryRouter(router.routes, { initialEntries: [path] })}
        />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}
describe("platform shell", () => {
  it("owns generic navigation without statically compiling finance pages", async () => {
    renderRoute("/");
    for (const name of ["tasks", "runs", "settings"])
      expect(await screen.findByTestId(`nav-${name}`)).toBeVisible();
    expect(
      screen.queryByTestId("nav-workflow-packages"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "专家模式" }));
    expect(await screen.findByTestId("nav-workflow-packages")).toBeVisible();
    expect(await screen.findByTestId("nav-resources")).toBeVisible();
    fireEvent.click(screen.getByRole("switch", { name: "专家模式" }));
    expect(screen.queryByTestId("nav-reports")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-templates")).not.toBeInTheDocument();
    expect(await screen.findByRole("main")).toHaveAttribute(
      "data-route-shell-mode",
      "scroll",
    );
  });
  it("gives the definition editor a full-height route shell", async () => {
    renderRoute("/workflow-packages/new");
    expect(await screen.findByRole("main")).toHaveAttribute(
      "data-route-shell-mode",
      "fullHeight",
    );
    const source = await screen.findByLabelText("Workflow Package YAML");
    expect(source).toBeVisible();
    fireEvent.change(source, { target: { value: "unfinished: [draft" } });
    fireEvent.click(screen.getByRole("switch", { name: "专家模式" }));
    fireEvent.click(screen.getByRole("switch", { name: "专家模式" }));
    expect(source).toHaveValue("unfinished: [draft");
  });
  it("does not restore historical product entry points", async () => {
    renderRoute("/templates");
    expect(
      await screen.findByRole("heading", { name: "Page not found" }),
    ).toBeVisible();
  });
});
