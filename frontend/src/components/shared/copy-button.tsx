import { useState } from "react";
import { Button } from "@/components/ui/button";

export function CopyButton({
  value,
  label,
  text = "复制 ID",
}: {
  value: string;
  label: string;
  text?: string;
}) {
  const [result, setResult] = useState("");
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        aria-label={label}
        onClick={() => {
          void (async () => {
            try {
              await navigator.clipboard.writeText(value);
              setResult("已复制");
            } catch {
              setResult("复制未完成，请手动选择文本");
            }
          })();
        }}
      >
        {text}
      </Button>
      {result && (
        <span role="status" className="text-xs text-muted-foreground">
          {result}
        </span>
      )}
    </span>
  );
}
