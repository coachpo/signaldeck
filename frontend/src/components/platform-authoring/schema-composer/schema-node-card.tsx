import { useMemo, useState } from "react";
import { Trash2 } from "lucide-react";

import {
  createDefaultSchemaNode,
} from "@/lib/platform-authoring/schema/factories";
import {
  formatPrimitiveList,
  parsePrimitiveInput,
  parsePrimitiveList,
  parseSchemaDefaultValueText,
  validateSchemaDefaultValue,
} from "@/lib/platform-authoring/schema/codec";
import { createLiteralValueDraft } from "@/lib/platform-authoring/schema/preview";
import type { JsonValue, SchemaIRLiteral, SchemaIRNode } from "@/lib/platform-authoring/schema/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import { DiscriminatedUnionEditor } from "./discriminated-union-editor";
import { ObjectFieldsEditor } from "./object-fields-editor";
import type { SchemaComposerNodeProps, SchemaNodeRenderer } from "./types";

type LiteralDraft = {
  kind: "boolean" | "integer" | "number" | "string";
  value: string;
};

type SchemaNodeCardProps = SchemaComposerNodeProps & {
  renderNode: SchemaNodeRenderer;
};

const kindOptions: SchemaIRNode["kind"][] = [
  "object",
  "string",
  "integer",
  "number",
  "boolean",
  "enum",
  "literal",
  "array",
  "ref",
  "discriminated_union",
];

function updateNodeMetadata(
  node: SchemaIRNode,
  key: "description" | "title",
  value: string,
): SchemaIRNode {
  return { ...node, [key]: value.trim() ? value : null };
}

function createDefaultLiteralDraft(node: SchemaIRNode): LiteralDraft {
  return node.kind === "literal"
    ? createLiteralValueDraft(node as SchemaIRLiteral)
    : { kind: "string", value: "value" };
}

function hasNodeDefaultValue(node: SchemaIRNode): node is SchemaIRNode & { defaultValue: JsonValue } {
  return Object.prototype.hasOwnProperty.call(node, "defaultValue");
}

function formatDefaultValueText(node: SchemaIRNode): string {
  return hasNodeDefaultValue(node) ? JSON.stringify(node.defaultValue, null, 2) : "";
}

function clearNodeDefaultValue<T extends SchemaIRNode>(node: T): T {
  const nextNode = { ...node };
  delete nextNode.defaultValue;
  return nextNode;
}

function formatDefaultIssueText(issue: { field: string; issue: string }): string {
  return issue.field === "defaultValue" ? issue.issue : `${issue.field}: ${issue.issue}`;
}

function preserveDefaultValueIfValid(nextNode: SchemaIRNode, currentNode: SchemaIRNode): SchemaIRNode {
  if (!hasNodeDefaultValue(currentNode)) {
    return nextNode;
  }

  return validateSchemaDefaultValue(nextNode, currentNode.defaultValue).length === 0
    ? { ...nextNode, defaultValue: currentNode.defaultValue }
    : nextNode;
}

export function SchemaNodeCard({
  depth = 0,
  label,
  node,
  onChange,
  onRemove,
  renderNode,
}: SchemaNodeCardProps) {
  const nodeDefaultText = formatDefaultValueText(node);
  const literalDraftSource =
    node.kind === "literal" ? JSON.stringify(node.value) : "";
  const [literalDraftState, setLiteralDraftState] = useState<{
    draft: LiteralDraft;
    source: string;
  }>(() => ({
    draft: createDefaultLiteralDraft(node),
    source: literalDraftSource,
  }));
  const defaultTextSource = `${node.kind}:${nodeDefaultText}`;
  const [defaultTextState, setDefaultTextState] = useState({
    source: defaultTextSource,
    text: nodeDefaultText,
  });
  const literalDraft =
    literalDraftState.source === literalDraftSource
      ? literalDraftState.draft
      : createDefaultLiteralDraft(node);
  const defaultText =
    defaultTextState.source === defaultTextSource
      ? defaultTextState.text
      : nodeDefaultText;
  const defaultTextResult = useMemo(
    () => parseSchemaDefaultValueText(node, defaultText),
    [defaultText, node],
  );
  const defaultIssue = defaultTextResult.issues[0];

  const handleDefaultTextChange = (value: string) => {
    setDefaultTextState({ source: defaultTextSource, text: value });
    const result = parseSchemaDefaultValueText(node, value);

    if (result.issues.length > 0) {
      return;
    }

    if (!result.hasDefault) {
      if (hasNodeDefaultValue(node)) {
        onChange(clearNodeDefaultValue(node));
      }
      return;
    }

    onChange({ ...node, annotationVersion: "signaldeck.schema/2", defaultValue: result.defaultValue });
  };

  const handleKindChange = (nextKind: SchemaIRNode["kind"]) => {
    const nextNode = preserveDefaultValueIfValid(
      {
        ...createDefaultSchemaNode(nextKind),
        ...(node.annotationVersion ? { annotationVersion: node.annotationVersion } : {}),
        ...(node.examples ? { examples: node.examples } : {}),
        description: node.description ?? null,
        title: node.title ?? null,
      },
      node,
    );
    onChange(nextNode);
  };

  return (
    <Card className={depth > 0 ? "bg-card/80" : undefined}>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex flex-col gap-1">
            <CardTitle className="text-base">{label}</CardTitle>
            <CardDescription>
              Adjust the supported builder subset and keep the structured authoring flow aligned.
            </CardDescription>
          </div>
          {onRemove ? (
            <Button size="sm" variant="outline" onClick={onRemove}>
              <Trash2 data-icon="inline-start" />
              Remove
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="flex flex-col gap-2">
            <Label>Node kind</Label>
            <Select value={node.kind} onValueChange={(value: SchemaIRNode["kind"]) => handleKindChange(value)}>
              <SelectTrigger aria-label={`${label} node kind`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {kindOptions.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Title</Label>
            <Input value={node.title ?? ""} onChange={(event) => onChange(updateNodeMetadata(node, "title", event.target.value))} />
          </div>
          <div className="flex flex-col gap-2">
            <Label>Description</Label>
            <Input value={node.description ?? ""} onChange={(event) => onChange(updateNodeMetadata(node, "description", event.target.value))} />
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <Label>Default value</Label>
          <Textarea
            aria-invalid={defaultIssue ? true : undefined}
            aria-label={`${label} default value`}
            className="font-mono text-xs"
            placeholder={'"example"'}
            rows={4}
            spellCheck={false}
            value={defaultText}
            onChange={(event) => handleDefaultTextChange(event.target.value)}
          />
          <p className="text-sm text-muted-foreground">
            Defaults initialize new input drafts only; explicit inputs are preserved. Enter JSON text; blank removes the annotation. Setting a default opts this node into signaldeck.schema/2.
          </p>
          {defaultIssue ? (
            <p className="text-sm text-destructive">{formatDefaultIssueText(defaultIssue)}</p>
          ) : null}
        </div>

        {node.kind === "object" ? (
          <ObjectFieldsEditor depth={depth} node={node} onChange={onChange} renderNode={renderNode} />
        ) : null}

        {node.kind === "array" ? (
          renderNode({
            depth: depth + 1,
            label: "Array items",
            node: node.items,
            onChange: (items) => onChange({ ...node, items }),
          })
        ) : null}

        {node.kind === "enum" ? (
          <div className="flex flex-col gap-2">
            <Label>Enum values</Label>
            <Textarea value={formatPrimitiveList(node.values)} rows={5} onChange={(event) => onChange({ ...node, values: parsePrimitiveList(event.target.value) })} />
            <p className="text-sm text-muted-foreground">
              Enter one value per line. Numbers and booleans keep their primitive types.
            </p>
          </div>
        ) : null}

        {node.kind === "literal" ? (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label>Literal type</Label>
              <Select
                value={literalDraft.kind}
                onValueChange={(value: LiteralDraft["kind"]) => {
                  const nextDraft = {
                    kind: value,
                    value: value === "boolean" ? "true" : literalDraft.value,
                  };
                  setLiteralDraftState({
                    draft: nextDraft,
                    source: literalDraftSource,
                  });
                  onChange({ ...node, value: parsePrimitiveInput(nextDraft.value, nextDraft.kind) });
                }}
              >
                <SelectTrigger aria-label={`${label} literal type`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="string">string</SelectItem>
                    <SelectItem value="integer">integer</SelectItem>
                    <SelectItem value="number">number</SelectItem>
                    <SelectItem value="boolean">boolean</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label>Literal value</Label>
              <Input
                value={literalDraft.value}
                onChange={(event) => {
                  const nextDraft = { ...literalDraft, value: event.target.value };
                  setLiteralDraftState({
                    draft: nextDraft,
                    source: literalDraftSource,
                  });
                  onChange({ ...node, value: parsePrimitiveInput(nextDraft.value, nextDraft.kind) });
                }}
              />
            </div>
          </div>
        ) : null}

        {node.kind === "ref" ? (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label>Schema key</Label>
              <Input value={node.schemaKey} onChange={(event) => onChange({ ...node, schemaKey: event.target.value })} />
            </div>
            <div className="flex flex-col gap-2">
              <Label>Schema version</Label>
              <Input
                value={node.schemaVersion ?? ""}
                onChange={(event) => {
                  const value = event.target.value.trim();
                  onChange({
                    ...node,
                    schemaVersion: value ? Number.parseInt(value, 10) : undefined,
                  });
                }}
              />
            </div>
          </div>
        ) : null}

        {node.kind === "discriminated_union" ? (
          <DiscriminatedUnionEditor depth={depth} label={label} node={node} onChange={onChange} renderNode={renderNode} />
        ) : null}
      </CardContent>
    </Card>
  );
}
