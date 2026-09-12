import { useCallback, useEffect, useMemo, useState } from "react";
import { ValueEditor } from "@/components/platform-authoring/generated-form/value-editor";
import type { InputHint } from "@/components/platform-authoring/generated-form/schema-form";
import { Button } from "@/components/ui/button";
import { InlineStatePanel } from "@/components/shared/inline-state-panel";
import { parseParameters } from "@/lib/platform-authoring/parameter-values";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";

export function LaunchInputs({
  schema,
  inputHints,
  label = "任务输入",
  value,
  onChange,
  onDirtyChange,
  initialJsonText = null,
  onJsonTextChange,
}: {
  schema: JsonObject;
  inputHints?: readonly InputHint[];
  technical?: boolean;
  label?: string;
  value: Json;
  onChange: (value: Json) => void;
  onDirtyChange: (dirty: boolean) => void;
  initialJsonText?: string | null;
  onJsonTextChange?: (text: string | null) => void;
}) {
  const [unfinished, setUnfinished] = useState(initialJsonText);
  const [downloadError, setDownloadError] = useState("");
  const recovery = useMemo(() => {
    if (unfinished === null) return null;
    try {
      return { value: parseParameters(unfinished) };
    } catch {
      return null;
    }
  }, [unfinished]);
  const validityChanged = useCallback(
    (valid: boolean) => onDirtyChange(unfinished !== null || !valid),
    [onDirtyChange, unfinished],
  );
  useEffect(() => {
    if (unfinished !== null) onDirtyChange(true);
  }, [onDirtyChange, unfinished]);

  function clearUnfinished() {
    setUnfinished(null);
    onJsonTextChange?.(null);
    setDownloadError("");
  }

  function downloadUnfinished() {
    if (unfinished === null) return;
    try {
      const url = URL.createObjectURL(
        new Blob([unfinished], { type: "text/plain;charset=utf-8" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = "未完成输入原稿.txt";
      link.click();
      URL.revokeObjectURL(url);
      setDownloadError("");
    } catch {
      setDownloadError(
        "下载未成功，原稿仍保留。请再次下载后再决定是否放弃修改。",
      );
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {unfinished !== null && (
        <InlineStatePanel
          tone="warning"
          title="发现未完成的输入修改"
          description={
            recovery
              ? "可以恢复后继续填写。恢复前，下方保留的是上次确认的内容。"
              : "上次修改没有填写完整，暂时无法恢复为表单。原稿仍完整保留，可先下载，或放弃这次修改后继续使用下方内容。"
          }
        >
          <div className="flex flex-wrap gap-2">
            {recovery && (
              <Button
                type="button"
                onClick={() => {
                  onChange(recovery.value);
                  clearUnfinished();
                }}
              >
                恢复未完成输入
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              onClick={downloadUnfinished}
            >
              下载未完成输入原稿
            </Button>
            <Button type="button" variant="ghost" onClick={clearUnfinished}>
              保留已确认内容，放弃未完成修改
            </Button>
          </div>
          {downloadError && (
            <p role="alert" className="mt-2 text-sm text-destructive">
              {downloadError}
            </p>
          )}
        </InlineStatePanel>
      )}
      <ValueEditor
        label={label}
        schema={schema}
        value={value}
        inputHints={inputHints}
        disabled={unfinished !== null}
        onValidityChange={validityChanged}
        onChange={onChange}
      />
    </div>
  );
}
