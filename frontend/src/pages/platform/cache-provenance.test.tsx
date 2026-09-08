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
  expect(screen.getByText("Cross-run cache reused")).toBeVisible();
  expect(screen.getByRole("link", { name: "source-run" })).toHaveAttribute(
    "href",
    "/runs/source-run",
  );
  expect(screen.getByText("source-operation")).toBeVisible();
  expect(screen.getByText(/Fetched 2026-09-08T08:00:00Z/)).toHaveTextContent(
    "cache expiry 2026-09-08T09:00:00Z",
  );
});
