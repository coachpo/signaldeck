import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useArtifact } from "@/hooks/use-workflow-platform";
import { Button } from "@/components/ui/button";
import { workflowPlatformApi } from "@/lib/api/workflow-platform";
import type { Json } from "@/lib/types/workflow-platform";
import type { ResultAttachment } from "@/lib/types/result";
import { RequestError } from "./feedback";
import { safePluginPageUrl } from "./plugin-links";
import { findArtifacts } from "./artifact-references";
const valueLabels: Record<string, string> = {
  title: "标题",
  text: "原文",
  question: "研究问题",
  symbols: "关注对象",
  includeRisk: "风险分析",
  summarize: "整理摘要",
  query: "查找范围",
  id: "记录编号",
  collection: "保存位置",
  createdAt: "创建时间",
  updatedAt: "更新时间",
  name: "名称",
  slug: "报告标识",
  reportId: "报告编号",
  sourceRunId: "来源运行",
  operationId: "操作编号",
  fetchedAt: "获取时间",
  observedAt: "资料时间",
  expiresAt: "有效至",
  url: "来源链接",
  content: "正文",
  location: "保存位置",
  asOf: "数据日期",
  price: "价格",
  symbol: "研究对象",
  isStale: "资料新鲜度",
  currency: "币种",
  provider: "数据提供方",
  previousClose: "前次收盘价",
  publishedAt: "发布时间",
};
export function ResultValue({ value }: { value: Json }) {
  if (value === null) return <span>未提供</span>;
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
        {typeof value === "boolean" ? (value ? "开启" : "关闭") : String(value)}
      </span>
    );
  return (
    <dl className="flex flex-col gap-2">
      {Object.entries(value).map(([key, child]) => (
        <div key={key} className="min-w-0">
          <dt className="text-xs text-muted-foreground">
            {valueLabels[key] ?? key}
          </dt>
          <dd className="pl-2">
            {key === "isStale" && typeof child === "boolean" ? (
              child ? (
                "已过期"
              ) : (
                "当前资料"
              )
            ) : (
              <ResultValue value={child} />
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}
export function ResultAttachmentView({
  attachment,
  pageUrl,
}: {
  attachment: ResultAttachment;
  pageUrl?: string | null;
}) {
  const [error, setError] = useState<unknown>(null);
  const refs = findArtifacts(attachment.reference);
  const reference = attachment.reference;
  let link =
    reference && typeof reference === "object" && !Array.isArray(reference)
      ? safePluginPageUrl(
          typeof reference.url === "string"
            ? reference.url
            : typeof reference.reportUrl === "string"
              ? reference.reportUrl
              : null,
        )
      : null;
  if (
    !link &&
    pageUrl &&
    reference &&
    typeof reference === "object" &&
    !Array.isArray(reference)
  ) {
    const base = safePluginPageUrl(pageUrl);
    if (base) {
      const url = new URL(base);
      if (typeof reference.slug === "string") {
        url.searchParams.set("report", reference.slug);
        link = url.href;
      } else if (
        typeof reference.reportId === "number" ||
        typeof reference.reportId === "string"
      ) {
        url.searchParams.set("reportId", String(reference.reportId));
        link = url.href;
      }
    }
  }
  return (
    <li className="flex flex-col gap-2 border-b border-border py-2">
      <span className="font-medium">{attachment.label}</span>
      {link && (
        <a
          className="text-sm underline"
          href={link}
          target="_blank"
          rel="noreferrer"
        >
          打开{attachment.kind === "report" ? "报告" : "保存记录"}
        </a>
      )}
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
      {!link && !refs.length && <ResultValue value={reference} />}
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
  const body =
    value && typeof value === "object" && !Array.isArray(value)
      ? [value.content, value.text, value.markdown].find(
          (v): v is string => typeof v === "string",
        )
      : typeof value === "string"
        ? value
        : undefined;
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
              <Markdown remarkPlugins={[remarkGfm]}>{body}</Markdown>
            </article>
          ) : (
            value !== undefined && <ResultValue value={value} />
          )}
        </>
      )}
    </div>
  );
}
