import { useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/shared/form-field";
export function JsonObjectEditor({
  label,
  value,
  onApply,
  onDraftChange,
}: {
  label: string;
  value: unknown;
  onApply: (value: Record<string, unknown>) => void;
  onDraftChange?: (dirty: boolean) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState("");
  const text = draft ?? JSON.stringify(value, null, 2);
  function apply() {
    try {
      const parsed: unknown = JSON.parse(text);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("Enter a JSON object.");
      onApply(parsed as Record<string, unknown>);
      setDraft(null);
      onDraftChange?.(false);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid JSON");
    }
  }
  return (
    <Field label={label} invalid={!!error}>
      <Textarea
        aria-label={label}
        aria-invalid={!!error}
        value={text}
        onChange={(e) => {
          setDraft(e.target.value);
          onDraftChange?.(true);
        }}
        spellCheck={false}
        className="min-h-40 font-mono text-xs"
      />
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button
        type="button"
        variant="outline"
        disabled={draft === null}
        onClick={apply}
      >
        Apply {label}
      </Button>
      {draft !== null && (
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setDraft(null);
            setError("");
            onDraftChange?.(false);
          }}
        >
          Discard {label} draft
        </Button>
      )}
    </Field>
  );
}
