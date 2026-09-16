"""Compile traceable discussion records without promoting qualitative judgments to facts."""

from finance_plugin.research_discussion_models import ResearchDiscussion
from finance_plugin.research_report_text import NUMERIC_OR_THRESHOLD, label

_STATUS_LABELS = {
    "accepted": "接受",
    "partially_accepted": "部分接受",
    "rejected": "不接受",
    "unresolved": "未决",
    "supported": "得到支持",
    "weakened": "被削弱",
    "retained": "保留",
    "revised": "修正",
    "withdrawn": "撤回",
}


def compile_discussion(
    discussion: ResearchDiscussion, eligible_ids: set[str]
) -> tuple[list[str], list[str], bool]:
    lines = [
        "",
        "## 结构化争议处理（定性内容均未核实）",
        "",
        (
            "仅校验阶段完整性、论点对应关系及证据引用资格，不证明推论正确；"
            "未决是有效的讨论结论。原始论点、回应、风险意见及裁决分别保留。"
        ),
    ]
    gaps: list[str] = []
    has_text = False
    all_ids: set[str] = set()
    side_ids: dict[str, set[str]] = {}
    for name, title, case in (
        ("bullCase", "看多方原始论点", discussion.bull_case),
        ("bearCase", "看空方原始论点", discussion.bear_case),
    ):
        lines += ["", f"### {title}", ""]
        ids: set[str] = set()
        side_ids[name] = ids
        if case is None or case.arguments is None:
            gaps.append(f"{title}：未提供此阶段。")
            lines.append("未提供此阶段。")
            continue
        if not case.arguments:
            gaps.append(f"{title}：未提供论点。")
            lines.append("未提供论点。")
        for index, argument in enumerate(case.arguments, start=1):
            location = f"{title}第{index}条"
            if argument.argument_id in all_ids:
                gaps.append(f"{location}：论点编号 {argument.argument_id} 重复。")
            all_ids.add(argument.argument_id)
            ids.add(argument.argument_id)
            has_text = has_text or bool(argument.statement.strip())
            lines.append(
                f"- 论点 {label(argument.argument_id)}（未核实）：{label(argument.statement)}"
                f"；证据 [{', '.join(label(key) for key in argument.evidence_ids)}]。"
            )
            gaps.extend(
                _record_gaps(location, argument.statement, argument.evidence_ids, eligible_ids)
            )
    stages = (
        (
            "bullResponse",
            "看多方对看空论点的回应",
            discussion.bull_response,
            "responses",
            side_ids["bearCase"],
        ),
        (
            "bearResponse",
            "看空方对看多论点的回应",
            discussion.bear_response,
            "responses",
            side_ids["bullCase"],
        ),
        ("riskReview", "风险意见", discussion.risk_review, "assessments", all_ids),
        ("adjudication", "逐项裁决", discussion.adjudication, "decisions", all_ids),
    )
    for _name, title, stage, collection, expected_ids in stages:
        lines += ["", f"### {title}", ""]
        if stage is None or getattr(stage, collection) is None:
            gaps.append(f"{title}：未提供此阶段。")
            lines.append("未提供此阶段。")
            continue
        records = getattr(stage, collection)
        if not records:
            lines.append("未提供记录。")
        seen: set[str] = set()
        for index, record in enumerate(records, start=1):
            location = f"{title}第{index}条"
            if record.argument_id not in all_ids:
                gaps.append(f"{location}：引用了不存在的论点 {record.argument_id}。")
            elif record.argument_id not in expected_ids:
                gaps.append(f"{location}：回应必须对应对方论点，{record.argument_id} 不属于对方。")
            if record.argument_id in seen:
                gaps.append(f"{location}：对论点 {record.argument_id} 的记录重复。")
            seen.add(record.argument_id)
            has_text = has_text or bool(record.rationale.strip())
            status = record.assessment if collection == "assessments" else record.disposition
            lines.append(
                f"- 论点 {label(record.argument_id)}：{_STATUS_LABELS[status]}"
                f"（未核实）；理由：{label(record.rationale)}"
                f"；证据 [{', '.join(label(key) for key in record.evidence_ids)}]。"
            )
            gaps.extend(_record_gaps(location, record.rationale, record.evidence_ids, eligible_ids))
        gaps.extend(
            f"{title}：未提供对论点 {argument_id} 的记录。"
            for argument_id in sorted(expected_ids - seen)
        )
    return lines, gaps, has_text


def _record_gaps(
    location: str, text: str, evidence_ids: list[str], eligible_ids: set[str]
) -> list[str]:
    gaps = []
    if not text.strip():
        gaps.append(f"{location}：定性说明为空。")
    if NUMERIC_OR_THRESHOLD.search(text):
        gaps.append(f"{location}：包含未经校验的数值或阈值论断，须通过结构化数值或显式阈值提交。")
    gaps.extend(
        f"{location}：引用的证据 {key} 不可用于结构化校验。"
        for key in evidence_ids
        if key not in eligible_ids
    )
    return gaps
