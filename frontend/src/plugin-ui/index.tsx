import { createRoot, type Root } from "react-dom/client";
import { flushSync } from "react-dom";
import { MarkdownContent } from "@/components/shared/markdown-content";
import { ConfirmDeleteDialog } from "@/components/shared/confirm-delete-dialog";
import { mountPluginShell } from "./shell";
import "./style.css";

const markdownRoots = new WeakMap<HTMLElement, Root>();

/** Render declared Markdown without changing the saved business text. */
export function renderMarkdown(target: HTMLElement, text: string) {
  let root = markdownRoots.get(target);
  if (!root) {
    root = createRoot(target);
    markdownRoots.set(target, root);
  }
  flushSync(() => root.render(
    <MarkdownContent components={{
      a: ({ href, children }) => /^https?:\/\//i.test(href ?? "")
        ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
        : <span>{children}</span>,
      img: ({ alt }) => <span>{alt}</span>,
    }}>{text}</MarkdownContent>,
  ));
}

export function confirmDelete(options: { title: string; description: string }): Promise<boolean> {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const trigger = document.activeElement;
  return new Promise((resolve) => {
    let settled = false;
    const finish = (confirmed: boolean) => {
      if (settled) return;
      settled = true;
      // Wait until the dialog's event dispatch completes before unmounting it.
      queueMicrotask(() => {
        root.unmount();
        host.remove();
        if (trigger instanceof HTMLElement) trigger.focus();
        resolve(confirmed);
      });
    };
    root.render(<ConfirmDeleteDialog {...options} open onConfirm={() => finish(true)} onOpenChange={(open) => { if (!open) finish(false); }} />);
  });
}

export const mountShell = mountPluginShell;
