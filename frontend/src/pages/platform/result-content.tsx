import { useState } from "react";
import { MarkdownContent } from "@/components/shared/markdown-content";
import { useArtifact } from "@/hooks/use-workflow-platform";
import { Button } from "@/components/ui/button";
import { workflowPlatformApi } from "@/lib/api/workflow-platform";
import type { Json } from "@/lib/types/workflow-platform";
import type { ResultAttachment } from "@/lib/types/result";
import { RequestError } from "./feedback";
import { safePluginPageUrl } from "./plugin-links";
import { findArtifacts } from "./artifact-references";
export function ResultValue({ value }: { value: Json }) {
  if (value === null) return <span>null</span>;
  if (Array.isArray(value))
    return (
      <ul className="flex flex-col gap-2">
        {value.map((item, index) => (
          <li key={index}>
            <ResultValue value={item} />
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
  return (
    <dl className="flex flex-col gap-2">
      {Object.entries(value).map(([key, child]) => (
        <div key={key} className="min-w-0">
          <dt className="text-xs text-muted-foreground">
            {key}
          </dt>
          <dd className="pl-2">
            <ResultValue value={child} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
export function ResultAttachmentView({
  attachment,
}: {
  attachment: ResultAttachment;
}) {
  const [error, setError] = useState<unknown>(null);
  const refs = findArtifacts(attachment.reference);
  const reference = attachment.reference;
  return (
    <li className="flex flex-col gap-2 border-b border-border py-2">
      <span className="font-medium">{attachment.label}</span>
      {refs.map(({ ref }) => (
        <div key={ref.digest} className="flex flex-col gap-2">
          <ArtifactReading digest={ref.digest} mediaType={ref.mediaType} />
          <Button
            key={ref.digest}
            variant="outline"
            onClick={() =>
              void workflowPlatformApi
                .downloadArtifact(ref.digest)
                .catch(setError)
            }
          >
            下载附件（{ref.mediaType}）
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
}: {
  digest: string;
  mediaType: string;
  initialOpen?: boolean;
}) {
  const [open, setOpen] = useState(initialOpen);
  const artifact = useArtifact(open ? digest : undefined);
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
          {body !== undefined ? (
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
