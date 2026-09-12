import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";
import { CacheProvenance } from "./cache-provenance";
it("links reused output to its originating run and preserves freshness timestamps", () => {
  render(
    <MemoryRouter>
      <CacheProvenance
        metadata={{
          cacheProvenance: {
            hit: true,
            sourceRunId: "source-run",
            sourceOperationId: "source-operation",
            fetchedAt: "2026-09-08T08:00:00Z",
            expiresAt: "2026-09-08T09:00:00Z",
            cacheKey: `sha256:${"a".repeat(64)}`,
          },
        }}
      />
    </MemoryRouter>,
  );
  expect(screen.getByText("沿用此前取得的资料")).toBeVisible();
  expect(screen.getByRole("link", { name: "查看资料来源步骤" })).toHaveAttribute(
    "href",
    "/runs/source-run?tab=evidence&operation=source-operation",
  );
  expect(screen.queryByText("source-operation")).not.toBeInTheDocument();
  expect(screen.queryByText(/sha256:/)).not.toBeInTheDocument();
  expect(screen.getByText(`取得时间：${new Date("2026-09-08T08:00:00Z").toLocaleString()}`)).toBeVisible();
  expect(screen.getByText(`可复用至：${new Date("2026-09-08T09:00:00Z").toLocaleString()}`)).toBeVisible();
});
