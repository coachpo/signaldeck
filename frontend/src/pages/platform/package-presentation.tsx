import { ChoiceField, Field, FieldGroup, TextField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import type { PresentationSection, WorkflowPresentation } from "@/lib/types/workflow-platform";
import { firstReference, sourceForReference, sourceSchema, type MappingSource } from "@/lib/platform-authoring/mapping-sources";
import { SourceChoice } from "./package-mapping";

export type PresentationToolChoice = {
  value: string;
  label: string;
  resultLinks?: { value: string; label: string }[];
  sourceValues?: string[];
};

type PresentationProps = {
  value: WorkflowPresentation | undefined;
  onChange: (value: WorkflowPresentation | undefined) => void;
  inputSources: MappingSource[];
  outputSources: MappingSource[];
  tools?: PresentationToolChoice[];
};

const sectionKinds = [
  { value: "markdown", label: "正文" }, { value: "value", label: "信息" },
  { value: "receipt", label: "操作回执" }, { value: "sources", label: "参考来源" },
  { value: "dataTime", label: "资料时间" }, { value: "notice", label: "提醒" },
  { value: "link", label: "查看服务中的结果" },
];

function ContentRequirement({ reference, sources, types }: { reference: string; sources: MappingSource[]; types: string[] }) {
  const source = sourceForReference(sources, reference);
  const schema = source && sourceSchema(source, reference);
  const expected = types.length === 1 && types[0] === "array" ? "一个列表" : types.includes("array") ? "一段文字或一个列表" : "一段文字";
  return schema && !types.includes(String(schema.type))
    ? <p className="text-sm text-destructive" role="alert">请继续选择{expected}作为内容。</p> : null;
}

function SectionEditor({ value, onChange, sources, tools, number }: {
  value: PresentationSection; onChange: (value: PresentationSection) => void;
  sources: MappingSource[]; tools: PresentationToolChoice[]; number: number;
}) {
  const label = `结果分节 ${number}`;
  const tool = value.kind === "link" ? tools.find((item) => item.value === value.toolId) : undefined;
  const linkSources = sources.filter((source) => source.value.startsWith("nodes.") && (!tool?.sourceValues || tool.sourceValues.includes(source.value)));
  const availableSources = value.kind === "link" ? linkSources : sources;
  const changeKind = (kind: string) => {
    const base = { ref: value.ref, label: value.label, ...(Object.hasOwn(value, "required") ? { required: value.required } : {}) };
    if (kind === "notice") onChange({ ...base, kind, severity: value.kind === "notice" ? value.severity : "info" });
    else if (kind === "link") {
      const firstTool = tools.find((item) => item.resultLinks?.length);
      const eligibleSources = sources.filter((source) => source.value.startsWith("nodes.") && (!firstTool?.sourceValues || firstTool.sourceValues.includes(source.value)));
      onChange({ ...base, kind, ref: firstReference(eligibleSources) ?? base.ref,
        toolId: firstTool?.value ?? "", linkKey: firstTool?.resultLinks?.[0]?.value ?? "" });
    } else onChange({ ...base, kind: kind as "markdown" | "value" | "receipt" | "sources" | "dataTime" });
  };
  const selectedTool = value.kind === "link" ? value.toolId : "";
  const selectedLink = value.kind === "link" ? value.linkKey : "";
  return (
    <Field label={label}>
      <TextField label={`${label} · 标题`} value={value.label} onChange={(text) => onChange({ ...value, label: text })} />
      <ChoiceField label={`${label} · 展示方式`} value={value.kind} onChange={changeKind} options={sectionKinds} />
      <SourceChoice label={`${label} · 内容`} value={value.ref} sources={availableSources} onChange={(ref) => onChange({ ...value, ref })} />
      {["markdown", "dataTime"].includes(value.kind) && <ContentRequirement reference={value.ref} sources={sources} types={["string"]} />}
      {value.kind === "notice" && <>
        <ContentRequirement reference={value.ref} sources={sources} types={["string", "array"]} />
        <ChoiceField label={`${label} · 提醒级别`} value={value.severity} onChange={(severity) => onChange({ ...value, severity: severity as "info" | "warning" | "missing" })}
          options={[{ value: "info", label: "一般提醒" }, { value: "warning", label: "需要留意" }, { value: "missing", label: "缺少信息" }]} />
      </>}
      {value.kind === "sources" && <ContentRequirement reference={value.ref} sources={sources} types={["array"]} />}
      {value.kind === "link" && <>
        <ChoiceField label={`${label} · 结果所属服务`} value={selectedTool || "__unselected__"} onChange={(next) => {
          const nextTool = tools.find((item) => item.value === next);
          const permitted = sources.filter((source) => source.value.startsWith("nodes.") && (!nextTool?.sourceValues || nextTool.sourceValues.includes(source.value)));
          const currentSource = sourceForReference(permitted, value.ref);
          onChange({ ...value, toolId: next, linkKey: nextTool?.resultLinks?.[0]?.value ?? "", ref: currentSource ? value.ref : firstReference(permitted) ?? value.ref });
        }} options={[
          ...(!tools.some((item) => item.value === selectedTool) ? [{ value: selectedTool || "__unselected__", label: selectedTool ? "已保存的服务（当前不可用）" : "请选择服务" }] : []),
          ...tools.filter((item) => item.resultLinks?.length || item.value === selectedTool).map(({ value: id, label: name }) => ({ value: id, label: name })),
        ]} disabled={!tools.length} />
        <ChoiceField label={`${label} · 打开页面`} value={selectedLink || "__unselected__"}
          onChange={(linkKey) => onChange({ ...value, linkKey })} options={[
            ...(!tool?.resultLinks?.some((item) => item.value === selectedLink) ? [{ value: selectedLink || "__unselected__", label: selectedLink ? "已保存的页面（当前不可用）" : "请选择结果页面" }] : []),
            ...(tool?.resultLinks ?? []),
          ]} disabled={!tool?.resultLinks?.length} />
        {!tool?.resultLinks?.length && <p className="text-sm text-muted-foreground">此服务目前没有可选结果页面。请在服务设置中连接提供结果页面的服务；已保存的页面选择会保留。</p>}
      </>}
      <label className="flex items-center gap-2 text-sm"><Checkbox checked={value.required === true}
        onCheckedChange={(checked) => onChange({ ...value, required: checked === true })} />缺少这部分时提醒我</label>
    </Field>
  );
}

export function PresentationEditor({ value, onChange, inputSources, outputSources, tools = [] }: PresentationProps) {
  const presentation: WorkflowPresentation = value ?? { version: "signaldeck.presentation/1" };
  const title = presentation.title;
  const hints = presentation.inputHints ?? [];
  const sections = presentation.sections ?? [];
  const titleInput = firstReference(inputSources, ["string"], true);
  const nextHint = firstReference(inputSources, ["string"], true, hints.map((hint) => hint.ref));
  const edit = (patch: Partial<WorkflowPresentation>) => onChange({ ...presentation, ...patch });
  const updateSection = (index: number, section: PresentationSection) => edit({ sections: sections.map((item, at) => at === index ? section : item) });
  return (
    <Field label="填写与阅读体验">
      <FieldGroup>
        <ChoiceField label="结果名称" value={title?.kind ?? "default"} options={[
          { value: "default", label: "使用任务名称" }, { value: "static", label: "使用固定名称" },
          ...(titleInput || title?.kind === "input" ? [{ value: "input", label: "使用填写的信息" }] : []),
        ]} onChange={(kind) => {
          if (kind === "default") { const { title: _removed, ...rest } = presentation; onChange(rest); }
          else if (kind === "static") edit({ title: { kind, text: "新结果" } });
          else edit({ title: { kind: "input", ref: titleInput ?? "" } });
        }} />
        {title?.kind === "static" && <TextField label="固定结果名称" value={title.text} onChange={(text) => edit({ title: { ...title, text } })} />}
        {title?.kind === "input" && <>
          <SourceChoice label="结果名称内容" value={title.ref} sources={inputSources} onChange={(ref) => edit({ title: { ...title, ref } })} />
          <ContentRequirement reference={title.ref} sources={inputSources} types={["string"]} />
        </>}
        <Field label="填写提示">
          {!hints.length && <p className="text-sm text-muted-foreground">可为文字输入设置多行填写和提示示例。</p>}
          {hints.map((hint, index) => <div key={index} className="flex flex-col gap-3 border-l border-border pl-3">
            <SourceChoice label={`填写提示 ${index + 1}`} value={hint.ref} sources={inputSources}
              onChange={(ref) => edit({ inputHints: hints.map((item, at) => at === index ? { ...item, ref } : item) })} />
            <ContentRequirement reference={hint.ref} sources={inputSources} types={["string"]} />
            {hints.some((other, at) => at !== index && other.ref === hint.ref) && <p role="alert" className="text-sm text-destructive">这项信息已有填写提示，请选择其他内容。</p>}
            <ChoiceField label={`填写提示 ${index + 1} · 输入框`} value={hint.control}
              onChange={(control) => edit({ inputHints: hints.map((item, at) => at === index ? { ...item, control: control as "text" | "textarea" } : item) })}
              options={[{ value: "text", label: "单行文字" }, { value: "textarea", label: "多行文字" }]} />
            <TextField label={`填写提示 ${index + 1} · 提示示例`} value={hint.placeholder ?? ""}
              onChange={(placeholder) => edit({ inputHints: hints.map((item, at) => at === index ? { ...item, placeholder } : item) })} />
            <Button type="button" variant="outline" aria-label={`移除填写提示 ${index + 1}`}
              onClick={() => edit({ inputHints: hints.filter((_, at) => at !== index) })}>移除提示</Button>
          </div>)}
          <Button type="button" variant="outline" disabled={!nextHint} onClick={() => {
            if (nextHint) edit({ inputHints: [...hints, { ref: nextHint, control: "text" }] });
          }}>添加填写提示</Button>
        </Field>
        <Field label="结果内容">
          {!sections.length && <p className="text-sm text-muted-foreground">结果将按原有信息展示。添加分节可以安排阅读顺序。</p>}
          {sections.map((section, index) => <div key={index} className="flex flex-col gap-3 border-l border-border pl-3">
            <SectionEditor value={section} number={index + 1} sources={outputSources} tools={tools} onChange={(next) => updateSection(index, next)} />
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" disabled={index === 0} aria-label={`结果分节 ${index + 1} 上移`} onClick={() => {
                const moved = [...sections]; [moved[index - 1], moved[index]] = [moved[index], moved[index - 1]]; edit({ sections: moved });
              }}>上移</Button>
              <Button type="button" variant="outline" aria-label={`移除结果分节 ${index + 1}`} onClick={() => edit({ sections: sections.filter((_, at) => at !== index) })}>移除分节</Button>
            </div>
          </div>)}
          <Button type="button" variant="outline" disabled={!outputSources.length} onClick={() => edit({
            sections: [...sections, { kind: "value", ref: firstReference(outputSources) ?? "", label: `结果内容 ${sections.length + 1}` }],
          })}>添加结果分节</Button>
        </Field>
        {value !== undefined && <Button type="button" variant="outline" onClick={() => onChange(undefined)}>恢复默认填写与阅读方式</Button>}
      </FieldGroup>
    </Field>
  );
}
