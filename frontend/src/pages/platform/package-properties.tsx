import {
  Field,
  FieldGroup,
  TextField,
  ChoiceField,
} from "@/components/shared/form-field";
import { JsonObjectEditor } from "@/components/shared/json-object-editor";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import type {
  AgentDefinition,
  WorkflowDefinition,
  NodeDefinition,
} from "@/lib/types/workflow-platform";

type Edit = (path: string[], value: unknown) => void;
type Props = { edit: Edit; draft: (id: string, dirty: boolean) => void };

function ObjectProperty({
  name,
  value,
  edit,
  draft,
}: Props & { name: string; value: unknown }) {
  return (
    <JsonObjectEditor
      label={name}
      value={value ?? {}}
      onApply={(v) => edit([name], v)}
      onDraftChange={(dirty) => draft(name, dirty)}
    />
  );
}
function NumberProperty({
  name,
  value,
  edit,
}: {
  name: string;
  value: number | undefined;
  edit: Edit;
}) {
  return (
    <TextField
      label={name}
      type="number"
      value={value === undefined ? "" : String(value)}
      onChange={(v) => edit([name], v === "" ? undefined : Number(v))}
    />
  );
}
function ListProperty({
  name,
  value,
  edit,
}: {
  name: string;
  value: string[] | undefined;
  edit: Edit;
}) {
  const items = Array.isArray(value) ? value : [];
  return (
    <Field label={name}>
      {items.map((item, index) => (
        <div key={index} className="flex items-end gap-2">
          <TextField
            label={`${name} ${index + 1}`}
            value={item}
            onChange={(v) =>
              edit(
                [name],
                items.map((old, i) => (i === index ? v : old)),
              )
            }
          />
          <Button
            variant="outline"
            aria-label={`移除 ${name} ${index + 1}`}
            onClick={() =>
              edit(
                [name],
                items.filter((_, i) => i !== index),
              )
            }
          >
            移除
          </Button>
        </div>
      ))}
      <Button variant="outline" onClick={() => edit([name], [...items, ""])}>
        添加 {name}
      </Button>
    </Field>
  );
}
export function AgentProperties({
  agent,
  edit,
  draft,
}: Props & { agent: AgentDefinition }) {
  const strategy = agent.strategy;
  return (
    <FieldGroup>
      <TextField
        label="Agent name"
        value={agent.name ?? ""}
        onChange={(v) => edit(["name"], v)}
      />
      <Field
        label="Strategy"
        description="切换策略类型请使用下方完整定义；显式修改并校验后保存。"
      >
        <p>{strategy?.kind ?? "未定义"}</p>
        {strategy?.kind === "model" && (
          <>
            <TextField
              label="Model resource"
              value={strategy.modelRef}
              onChange={(v) => edit(["strategy", "modelRef"], v)}
            />
            <Textarea
              aria-label="Prompt"
              value={strategy.prompt}
              onChange={(e) => edit(["strategy", "prompt"], e.target.value)}
              className="min-h-40"
            />
          </>
        )}
        {strategy?.kind === "deterministic" && (
          <>
            <TextField
              label="Deterministic tool"
              value={strategy.toolId}
              onChange={(v) => edit(["strategy", "toolId"], v)}
            />
            {["inputMapping", "outputMapping"].map((name) => (
              <ObjectProperty
                key={name}
                name={name}
                value={strategy[name as "inputMapping" | "outputMapping"]}
                edit={(path, value) => edit(["strategy", ...path], value)}
                draft={(id, dirty) => draft(`strategy.${id}`, dirty)}
              />
            ))}
          </>
        )}
      </Field>
      <ListProperty name="tools" value={agent.tools} edit={edit} />
      <ListProperty name="resources" value={agent.resources} edit={edit} />
      <Field
        label="预算"
        description="留空继承合同默认值；不会因模式切换重置。"
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {(
            [
              "maxModelRequests",
              "maxToolCalls",
              "maxTokens",
              "deadlineSeconds",
              "maxParallelTools",
            ] as const
          ).map((name) => (
            <NumberProperty
              key={name}
              name={name}
              value={agent.budget?.[name]}
              edit={(path, value) => edit(["budget", ...path], value)}
            />
          ))}
        </div>
      </Field>
      {(["inputSchema", "outputSchema", "toolCache"] as const).map((name) => (
        <ObjectProperty
          key={name}
          name={name}
          value={agent[name]}
          edit={edit}
          draft={draft}
        />
      ))}
    </FieldGroup>
  );
}
export function WorkflowProperties({
  workflow,
  edit,
  draft,
}: Props & { workflow: WorkflowDefinition }) {
  return (
    <FieldGroup>
      <TextField
        label="Workflow name"
        value={workflow.name ?? ""}
        onChange={(v) => edit(["name"], v)}
      />
      <ChoiceField
        label="failurePolicy"
        value={workflow.failurePolicy ?? "continue_independent"}
        onChange={(v) => edit(["failurePolicy"], v)}
        options={[
          { value: "continue_independent", label: "独立分支继续" },
          { value: "fail_fast", label: "失败即停止" },
        ]}
      />
      <NumberProperty
        name="maxParallelNodes"
        value={workflow.maxParallelNodes}
        edit={edit}
      />
      <NumberProperty
        name="deadlineSeconds"
        value={workflow.deadlineSeconds}
        edit={edit}
      />
      <ObjectProperty key={workflow.presentation === undefined ? "absent-presentation" : "present-presentation"} name="presentation" value={workflow.presentation} edit={edit} draft={draft} />
      {workflow.presentation !== undefined && (
        <Button variant="outline" onClick={() => { edit(["presentation"], undefined); draft("presentation", false); }}>
          移除 presentation
        </Button>
      )}
      {(["inputSchema", "outputSchema", "outputMapping"] as const).map(
        (name) => (
          <ObjectProperty
            key={name}
            name={name}
            value={workflow[name]}
            edit={edit}
            draft={draft}
          />
        ),
      )}
    </FieldGroup>
  );
}
export function NodeProperties({
  node,
  edit,
  draft,
}: Props & { node: NodeDefinition }) {
  return (
    <FieldGroup>
      <TextField
        label="Agent reference (uses)"
        value={node.uses ?? ""}
        onChange={(v) => edit(["uses"], v)}
      />
      <ObjectProperty
        name="inputMapping"
        value={node.inputMapping}
        edit={edit}
        draft={draft}
      />
      <Field
        label="额外控制依赖"
        description="输入引用与条件引用自动推导依赖；这里只需补充执行顺序。"
      >
        <ListProperty name="dependsOn" value={node.dependsOn} edit={edit} />
      </Field>
      <ObjectProperty
        name="condition"
        value={node.condition}
        edit={edit}
        draft={draft}
      />
      {node.condition && (
        <Button
          variant="outline"
          onClick={() => edit(["condition"], undefined)}
        >
          移除条件
        </Button>
      )}
      <ListProperty
        name="acceptUpstreamStates"
        value={node.acceptUpstreamStates}
        edit={edit}
      />
      <NumberProperty name="maxAttempts" value={node.maxAttempts} edit={edit} />
    </FieldGroup>
  );
}
