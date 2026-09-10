import type { Json, WorkflowDefinition } from "./workflow-platform";
export interface TaskDraftWrite {
  revision: number;
  name: string;
  packageKey: string;
  workflowKey: string;
  packageHash: string;
  sourceRunId: string | null;
  hasParameters: boolean;
  parameters: Json;
  jsonText: string | null;
  launchId: string;
  pending: boolean;
  bindingToken: string | null;
}
export interface TaskDraft extends TaskDraftWrite {
  id: string;
  updatedAt: string;
  currentPackageHash: string | null;
  needsRevalidation: boolean;
  workflow: WorkflowDefinition;
}
