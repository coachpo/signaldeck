import type { AgentDefinition, ExecutionOptions, Json, WorkflowDefinition } from "./workflow-platform";
export interface TaskDraftWrite {
  revision: number;
  name: string;
  packageKey: string;
  workflowKey: string;
  packageHash: string;
  sourceRunId: string | null;
  hasParameters: boolean;
  parameters: Json;
  executionOptions?: ExecutionOptions;
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
  agents?: Record<string, AgentDefinition>;
}
