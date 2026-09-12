import { useState } from "react";
import { MarkdownContent } from "@/components/shared/markdown-content";
import { useArtifact } from "@/hooks/use-workflow-platform";
import { Button } from "@/components/ui/button";
import { workflowPlatformApi } from "@/lib/api/workflow-platform";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";
import type { ResultAttachment } from "@/lib/types/result";
import { RequestError } from "./feedback";
import { safePluginPageUrl } from "./plugin-links";
import { findArtifacts } from "./artifact-references";
import { objectValue } from "./result-context";
import { projectedArtifactValues, type ArtifactPresentation } from "./result-artifact-presentation";
export function ResultValue({ value, schema }: { value: Json; schema?: JsonObject }) {
  if (value === null) return <span>null</span>;
  if (Array.isArray(value))
    return (
      <ul className="flex flex-col gap-2">
        {value.map((item, index) => (
          <li key={index}>
            <ResultValue value={item} schema={objectValue(schema?.items)} />
          </li>
        ))}
      </ul>
    );
  if (typeof value === "string" && safePluginPageUrl(value))
    return (
      <a
        className="break-all underline"
        href={safePluginPageUrl(value)!}
        target="_blank"
        rel="noreferrer"
      >
        {value}
      </a>
    );
  if (typeof value !== "object")
    return (
      <span className="whitespace-pre-wrap break-words">
        {String(value)}
      </span>
    );
  const artifact = findArtifacts(value).find(({ path }) => path === "$" || path === "$.$artifact");
  if (artifact) return <ul><ResultAttachmentView attachment={{ kind: "artifact", label: "结果附件", reference: value }} /></ul>;
  return (
    <dl className="flex flex-col gap-2">
      {Object.entries(value).map(([key, child]) => (
        <div key={key} className="min-w-0">
          <dt className="text-xs text-muted-foreground">
            {String(objectValue(objectValue(schema?.properties)?.[key])?.title ?? key)}
          </dt>
          <dd className="pl-2">
            <ResultValue value={child} schema={objectValue(objectValue(schema?.properties)?.[key])} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
export function ResultAttachmentView({
  attachment,
  presentation,
  pending = false,
}: {
  attachment: ResultAttachment;
  presentation?: ArtifactPresentation;
  pending?: boolean;
}) {
  const [error, setError] = useState<unknown>(null);
  const refs = findArtifacts(attachment.reference);
  const reference = attachment.reference;
  return (
    <li className="flex flex-col gap-2 border-b border-border py-2">
      <span className="font-medium">{attachment.label}</span>
      {refs.map(({ ref }) => (
        <div key={ref.digest} className="flex flex-col gap-2">
          {pending ? <p role="status">正在准备附件阅读…</p> : <ArtifactReading digest={ref.digest} mediaType={ref.mediaType} presentation={presentation} />}
          <Button
            key={ref.digest}
            variant="outline"
            onClick={() =>
              void workflowPlatformApi
                .downloadArtifact(ref.digest, attachment.label)
                .catch(setError)
            }
          >
            {presentation ? "下载原始附件" : `下载附件（${ref.mediaType}）`}
          </Button>
        </div>
      ))}
      {!refs.length && <ResultValue value={reference} />}
      <RequestError error={error} />
    </li>
  );
}

export function ArtifactReading({
  digest,
  mediaType,
  initialOpen = false,
  presentation,
}: {
  digest: string;
  mediaType: string;
  initialOpen?: boolean;
  presentation?: ArtifactPresentation;
}) {
  const [open, setOpen] = useState(initialOpen);
  const artifact = useArtifact(open ? digest : undefined);
  if (presentation?.unavailable) return <p className="text-sm text-muted-foreground">附件正文暂时无法展开。已确认的内容可在结果页阅读，也可下载原始附件核对。</p>;
  if (!mediaType.startsWith("text/") && !mediaType.includes("json"))
    return null;
  let value: Json | undefined = artifact.data;
  if (typeof value === "string" && mediaType.includes("json")) {
    try {
      value = JSON.parse(value) as Json;
    } catch {
      /* The stored bytes remain available for direct reading. */
    }
  }
  const body = !mediaType.includes("json") && typeof value === "string" ? value : undefined;
  const projected = presentation && typeof artifact.data === "string" ? projectedArtifactValues(artifact.data, mediaType, presentation) : undefined;
  return (
    <div className="flex flex-col gap-2">
      <Button variant="outline" onClick={() => setOpen((v) => !v)}>
        {open ? "收起附件正文" : "阅读附件正文"}
      </Button>
      {open && (
        <>
          <RequestError
            error={artifact.error}
            retry={() => void artifact.refetch()}
          />
          {artifact.isPending && <p>正在读取正文…</p>}
          {projected && presentation && projected.length > 0 && projected.length < presentation.sections.length && <p className="text-sm">部分内容尚未展开，下面只显示能够读取的部分。可下载原始附件核对。</p>}
          {projected ? projected.length ? <div className="flex flex-col gap-3">{projected.map((section, index) => <section key={index} aria-label={section.label} className="flex flex-col gap-2">
            <h3 className="font-medium">{section.label}</h3>
            {section.kind === "receipt" ? <p>此项保存已确认。</p> : section.kind === "markdown" && typeof section.value === "string" ? <MarkdownContent>{section.value}</MarkdownContent> : <ResultValue value={section.value} />}
          </section>)}</div> : <p>所选正文尚未展开。可下载原始附件核对；这不表示资料缺失或保存失败。</p> : body !== undefined ? (
            <article className="min-w-0 overflow-x-auto text-sm">
              <MarkdownContent>{body}</MarkdownContent>
            </article>
          ) : (
            value !== undefined && <ResultValue value={value} />
          )}
        </>
      )}
    </div>
  );
}
