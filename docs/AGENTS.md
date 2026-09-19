# Docs Guide

The [document index](README.md) names the single authority for each fact. When a fact changes, edit its authority first, then fix or shorten the summaries that link to it. When a document is added, removed or changes scope, update the index, and the root README's document list if it names that document.

- Canonical documents keep their existing paths and stay in Chinese, including the English-named `data-model.md` and `writing-extensions.md`; agent guides stay in English. Do not add a second canonical path or a bilingual counterpart without an explicit language migration.
- Link documents and repository files with relative links instead of copying their rules.
- Ground scope, behavior and deployment statements in source, configuration or verified results.
- Examples and commands keep secrets redacted and never present credentials as readable product data.
- Three managed regions exist: `write-project-docs:document-navigation` in the root `AGENTS.md`, `write-project-docs:shared-contributing` in `CONTRIBUTING.md` and `write-project-docs:development-source-size` in `开发规范.md`. No generator maintains them: edit their content directly and keep the start and end markers.
