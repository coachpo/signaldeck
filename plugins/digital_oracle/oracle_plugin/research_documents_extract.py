"""Readable bounded passages from source HTML, with stable normalized-text locations."""

import re
from datetime import datetime
from html.parser import HTMLParser

from plugin_runtime.common import CamelModel
from pydantic import Field


class DocumentPassage(CamelModel):
    title: str
    locator: str
    text: str = Field(max_length=6000)


class OriginalHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool]] = []
        self.published: datetime | None = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        hidden = (
            tag in ("script", "style", "noscript", "ix:header", "ix:hidden", "head")
            or bool(
                re.search(
                    r"display\s*:\s*none|visibility\s*:\s*hidden", values.get("style") or "", re.I
                )
            )
            or "hidden" in values
        )
        if tag == "meta" and values.get("property", values.get("name", "")) in (
            "article:published_time",
            "datePublished",
        ):
            from .research_documents import timestamp

            self.published = timestamp(values.get("content"))
        if tag not in ("meta", "link", "br", "hr", "img", "input", "source", "wbr"):
            self.stack.append((tag, hidden or any(h for _, h in self.stack)))
        if not any(h for _, h in self.stack):
            if tag in ("p", "div", "tr", "h1", "h2", "h3", "br", "li"):
                self.parts.append("\n")
            elif tag in ("td", "th"):
                self.parts.append(" | ")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if not any(h for _, h in self.stack) and tag in ("p", "div", "tr", "h1", "h2", "h3", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not any(h for _, h in self.stack):
            self.parts.append(data)

    def body(self):
        return "\n".join(
            " ".join(p.split()).strip(" |")
            for p in "".join(self.parts).splitlines()
            if p.strip(" |\t")
        )


def select_passages(body: str) -> list[DocumentPassage]:
    """Prefer substantive section headings over cover sheets and table-of-contents rows."""
    if len(body) <= 24000:
        windows = [
            (start, min(start + 6000, len(body)), "Document text")
            for start in range(0, len(body), 6000)
        ]
    else:
        windows = []
        sections = [
            ("Management discussion", r"management.{0,65}discussion"),
            ("Results of operations", r"results of operations"),
            ("Outlook and guidance", r"outlook|guidance"),
            (
                "Financial statements",
                r"consolidated.{0,40}(?:statements|balance)|financial statements",
            ),
            ("Liquidity", r"liquidity and capital resources"),
        ]
        for title, pattern in sections:
            candidates = []
            for match in re.finditer(r"(?im)^.{0,30}(?:" + pattern + r").{0,120}$", body):
                heading = match.group().strip()
                # TOC links commonly end in a page number and are not the actual section.
                if re.search(r"\s\d{1,3}$", heading) or heading.count("|") > 1:
                    continue
                candidates.append(match.start())
            if candidates:
                start = candidates[0] if title == "Financial statements" else candidates[-1]
                if not any(a <= start < b for a, b, _ in windows):
                    windows.append((start, min(start + 4800, len(body)), title))
        if not windows:
            windows = [(0, 6000, "Document opening; requested sections not identified")]
        windows.sort()
    return [
        DocumentPassage(
            title=title,
            locator=(
                f"normalized text characters {start + 1}-{end}; "
                f"paragraph {body[:start].count(chr(10)) + 1}"
            ),
            text=body[start:end],
        )
        for start, end, title in windows[:5]
    ]
