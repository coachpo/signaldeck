import type { Json, JsonObject, WorkflowDefinition } from "./workflow-platform";
export interface Preparation {
  packageKey: string;
  workflowKey: string;
  packageHash: string;
  ready: boolean;
  bindingToken: string | null;
  requirements: Requirement[];
  issues: string[];
  changedBindings: string[];
  previousBindings: JsonObject;
  effectiveSettings: JsonObject;
}
export interface Requirement {
  id: string;
  kind: "model" | "tool" | "plugin";
  name: string;
  configured: boolean;
  hasCredentials: boolean;
  config: JsonObject;
  observation: "not_observed" | "succeeded" | "failed" | "unknown";
  observedAt?: string | null;
  observationError?: string | null;
  issue?: string | null;
}
export interface ReuseInput {
  workflow: WorkflowDefinition;
  sourceRunId: string;
  packageKey: string;
  workflowKey: string;
  packageHash: string;
  parameters: Json;
  inputSchema: JsonObject;
}
export interface TaskPreset {
  id: string;
  name: string;
  packageKey: string;
  workflowKey: string;
  packageHash: string;
  parameters: Json;
  hasParameters: boolean;
  isFavorite: boolean;
  isPinned: boolean;
  currentPackageHash: string | null;
  needsRevalidation: boolean;
  validationStatus: "valid" | "invalid" | "unavailable" | "not_applicable";
  validationErrors: Json[];
}
export type PresetWrite = Pick<
  TaskPreset,
  | "name"
  | "packageKey"
  | "workflowKey"
  | "packageHash"
  | "parameters"
  | "hasParameters"
  | "isFavorite"
  | "isPinned"
>;
export interface PrepareInput {
  packageKey: string;
  workflowKey: string;
  parameters: Json;
  revisionHash?: string;
  sourceRunId?: string;
}
export interface ConnectionPreset {
  id: string;
  name: string;
  description: string;
  resourceId: string;
  kind: "model" | "tool";
  config: JsonObject;
  credentialFields: { key: string; label: string; required: boolean }[];
}
