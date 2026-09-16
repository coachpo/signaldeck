"""Safe report labels and the shared qualitative assertion boundary."""

import html
import re

# Narrative is never treated as verified. Numeric/threshold assertions must enter
# the structured path even when they repeat a value found elsewhere in the report.
NUMERIC_OR_THRESHOLD = re.compile(
    r"\d|[%％±<>≤≥]|[零〇一二三四五六七八九十百千万亿两]+\s*(?:成|倍|元|美元|股|点|%)"
    r"|落空|超预期|不及预期|阈值|低于|高于|突破|超过|指引|至少|至多|翻倍|减半"
    r"|\b(?:threshold|guidance|beat|miss|above|below|greater|less|percent|double|half"
    r"|zero|one|two|three|four|five|six|seven|eight|nine|ten|hundred|million|billion)\b",
    re.IGNORECASE,
)


def label(value: str) -> str:
    escaped = html.escape(value.replace("\n", " ").replace("\r", " "), quote=False)
    for character in "#`*_[]":
        escaped = escaped.replace(character, f"&#{ord(character)};")
    return escaped
