import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/** Shared typography for explicitly selected Markdown content. */
export function MarkdownContent({ children, components }: {
  children: string;
  components?: Components;
}) {
  return (
    <div className="markdown-preview min-w-0 max-w-full">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => (
            <pre tabIndex={0} aria-label="代码块">{children}</pre>
          ),
          table: ({ children }) => (
            <div className="max-w-full overflow-x-auto" role="region" aria-label="表格" tabIndex={0}>
              <table>{children}</table>
            </div>
          ),
          ...components,
        }}
      >
        {children}
      </Markdown>
    </div>
  );
}
