import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { SafeSettings } from "./task-preparation";
import { connectionName } from "./task-labels";

it("keeps arbitrary scope keys and values literal, even when named like former business aliases", () => {
  render(<SafeSettings value={{ collection: "model", accountId: "name", scope: { includeRisk: false, reportId: "resources" } }} />);
  for (const text of ["collection", "model", "accountId", "name", "scope", "includeRisk", "reportId", "resources"]) expect(screen.getByText(text)).toBeVisible();
  expect(connectionName("", "example/notes")).toBe("example/notes");
  expect(connectionName("Operator name", "example/notes")).toBe("Operator name");
});
