export type Json =
  null | boolean | number | string | Json[] | { [key: string]: Json };
export type JsonObject = { [key: string]: Json };
export interface AgentDefinition {
  name?: string;
  inputSchema: JsonObject;
  outputSchema: JsonObject;
  strategy:
    | { kind: "model"; modelRef: string; prompt: string }
    | {
        kind: "deterministic";
        toolId: string;
        inputMapping?: JsonObject;
        outputMapping?: JsonObject;
      };
  tools?: string[];
  toolCache?: Record<
    string,
    { ttlSeconds: number; scope?: "resource"; key?: "release_input_resources" }
  >;
  resources?: string[];
  budget?: {
    maxModelRequests?: number;
    maxToolCalls?: number;
    maxTokens?: number;
    maxOutputTokens?: number;
    deadlineSeconds?: number;
    maxParallelTools?: number;
  };
}
export interface NodeDefinition {
  uses: string;
  dependsOn?: string[];
  inputMapping: JsonObject;
  condition?: JsonObject | null;
  acceptUpstreamStates?: string[];
  maxAttempts?: number;
}
export type PresentationSection =
  | { kind: "markdown" | "value" | "receipt" | "sources" | "dataTime"; ref: string; label: string; required?: boolean }
  | { kind: "notice"; ref: string; label: string; required?: boolean; severity: "info" | "warning" | "missing" }
  | { kind: "link"; ref: string; label: string; required?: boolean; toolId: string; linkKey: string };
export interface WorkflowPresentation {
  version: "signaldeck.presentation/1";
  inputHints?: { ref: string; control: "text" | "textarea"; placeholder?: string }[];
  title?: { kind: "input"; ref: string } | { kind: "static"; text: string };
  sections?: PresentationSection[];
}
export interface WorkflowDefinition {
  description?: string;
  presentation?: WorkflowPresentation;
  name?: string;
  inputSchema: JsonObject;
  outputSchema: JsonObject;
  nodes: Record<string, NodeDefinition>;
  outputMapping: JsonObject;
  maxParallelNodes?: number;
  deadlineSeconds?: number;
  failurePolicy?: "continue_independent" | "fail_fast";
}
export interface PackageDefinition {
  apiVersion: "signaldeck.workflowPackage/v2";
  metadata: { key: string; name: string; description?: string };
  agents: Record<string, AgentDefinition>;
  workflows: Record<string, WorkflowDefinition>;
}
export interface DependencyEdge {
  source: string;
  target: string;
  sources: ("control" | "input" | "condition")[];
  paths: string[];
}
export interface WorkflowPlan {
  workflowKey: string;
  nodeOrder: string[];
  dependencies: Record<string, string[]>;
  edges: DependencyEdge[];
}
export interface Diagnostic {
  code: string;
  path: string;
  message: string;
  line?: number | null;
  column?: number | null;
}
export interface ValidationResult {
  definition: PackageDefinition | null;
  plans: Record<string, WorkflowPlan> | null;
  contentHash: string | null;
  diagnostics: Diagnostic[];
}
export interface WorkflowPackage {
  id: string;
  key: string;
  name: string;
  description: string;
  source: string;
  definition: PackageDefinition;
  plans: Record<string, WorkflowPlan>;
  packageHash: string;
  createdAt: string;
  updatedAt: string;
}
export type RunStatus =
  "queued" | "running" | "succeeded" | "failed" | "cancelled";
export interface LaunchOrigin {
  kind: "manual" | "rerun" | "reuse" | "schedule";
  sourceRunId?: string | null;
  scheduleId?: string | null;
  triggerId?: string | null;
  scheduledAt?: string | null;
}
export interface RunSummary {
  hasUnknownEffects?: boolean;
  hasUnknownResults?: boolean;
  id: string;
  packageKey: string;
  workflowKey: string;
  packageHash: string;
  status: RunStatus;
  createdAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  cancelRequestedAt?: string | null;
  origin: LaunchOrigin;
}
export interface ExecutionEvidence {
  id: string;
  runId: string;
  parentId: string | null;
  nodeId: string;
  kind: "node" | "agent" | "model" | "tool" | "attempt";
  status:
    | "pending"
    | "running"
    | "succeeded"
    | "failed"
    | "blocked"
    | "skipped"
    | "cancelled"
    | "unknown"
    | "timed_out";
  attempt: number;
  operationId?: string | null;
  toolId?: string | null;
  input: Json;
  output: Json;
  errorCode?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  metadata: JsonObject;
}
export interface RunDetail extends RunSummary {
  spec: {
    runId: string;
    packageKey: string;
    workflowKey: string;
    packageHash: string;
    definition: PackageDefinition;
    plan: WorkflowPlan;
    parameters: Json;
    modelBindings: JsonObject;
    pluginReleases: JsonObject[];
    resourceBindings: JsonObject;
    toolAliases: Record<string, string>;
    coreArtifact: string;
    deadline: string;
    origin: LaunchOrigin;
  };
  output: Json;
  errorCode?: string | null;
  evidence: ExecutionEvidence[];
}
export type ModelErrorCategory = "quota" | "authentication" | "rate_limit" | "model" | "input" | "output_limit" | "unknown";
export interface ModelObservation {
  status: "not_observed" | "succeeded" | "failed" | "unknown";
  observedAt: string | null;
  errorCode: string | null;
  errorCategory: ModelErrorCategory | null;
  runId: string | null;
  evidenceId: string | null;
}
export interface Resource {
  modelObservation?: ModelObservation | null;
  resourceId: string;
  kind: "model" | "tool";
  config: JsonObject;
  hasCredentials: boolean;
  credentialRevision: string;
}
export interface ResourceWrite {
  resourceId: string;
  kind: "model" | "tool";
  config: JsonObject;
  credentials?: Record<string, string>;
}
export interface PluginRelease {
  pluginId: string;
  releaseId: string;
  artifactDigest: string;
  contractDigest: string;
  endpoint: string;
  protocolVersion: string;
  tools: JsonObject[];
  configSchema: JsonObject;
  supportsOperationQuery: boolean;
  supportsOperationDeduplication: boolean;
  pageUrl?: string | null;
}
export interface Plugin {
  pluginId: string;
  release: PluginRelease;
  enabled: boolean;
  health: {
    status: "not_observed" | "succeeded" | "failed" | "unknown";
    observedAt: string | null;
    errorCode: string | null;
    runId: string | null;
    operationId: string | null;
    evidenceId: string | null;
  };
}
export interface ScheduleConfig {
  creationId?: string;
  id?: string;
  name: string;
  packageKey: string;
  workflowKey: string;
  parameters: Json;
  cron: string;
  timeZone: string;
  overlapPolicy: "skip" | "buffer_one" | "allow";
  catchupWindowSeconds: number;
  paused: boolean;
}
export interface Schedule extends ScheduleConfig {
  id: string;
  revision: number;
  syncedRevision: number | null;
  syncStatus: "pending" | "synced" | "failed" | "deleted";
  syncErrorCode: string | null;
  desiredDeleted?: boolean;
  updatedAt?: string;
}
export interface ScheduleFire {
  triggerId: string;
  scheduleId: string;
  scheduledAt: string;
  engineWorkflowId: string;
  engineRunId: string;
  status:
    | "pending"
    | "launched"
    | "launch_failed"
    | "succeeded"
    | "failed"
    | "cancelled";
  runId: string | null;
  errorCode: string | null;
  updatedAt: string;
}
export interface ArtifactRef {
  digest: string;
  sizeBytes: number;
  mediaType: string;
}
