"""Compile the canonical research body without creating or changing a report."""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from decimal import Decimal

from finance_plugin.research_evidence import ResearchReportOutput
from finance_plugin.research_report_display import limitation_label, metric_label
from finance_plugin.research_report_input import parse_report_input
from finance_plugin.research_report_validation import (
    claim_problem,
    day_end,
    derived_problem,
    evidence_problem,
    threshold_problem,
)
from plugin_runtime.serialization import project

# Narrative is never treated as verified. Numeric/threshold assertions must enter
# the structured path even when they repeat a value found elsewhere in the report.
_NUMERIC_OR_THRESHOLD = re.compile(
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


def compile_research_report(arguments: dict, *, now: datetime | None = None) -> dict:
    request, invalid_items = parse_report_input(arguments)
    frozen_now = now or datetime.now(UTC)
    if frozen_now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    cutoff = min(day_end(request.as_of_date), request.cutoff_at or frozen_now, frozen_now)
    gaps = [*request.upstream_gaps, *invalid_items]
    evidence = {}
    eligible = {}
    duplicate_ids = set()
    superseded_ids = {
        item.supersedes_evidence_id for item in request.evidence if item.supersedes_evidence_id
    }
    for item in request.evidence:
        if item.evidence_id in evidence:
            if item != evidence[item.evidence_id]:
                gaps.append(f"{item.evidence_id}: conflicting duplicate evidence identity")
                duplicate_ids.add(item.evidence_id)
            continue
        evidence[item.evidence_id] = item
        # Revision archives remain traceable without being mistaken for missing
        # current research. References to these IDs still fail claim validation.
        if item.evidence_id in superseded_ids:
            continue
        problem = evidence_problem(item, cutoff)
        if item.symbol and item.symbol.casefold() != request.symbol.casefold():
            problem = "evidence symbol differs from research symbol"
        if problem:
            gaps.append(f"{item.evidence_id}: {problem}")
        else:
            eligible[item.evidence_id] = item
    for key in duplicate_ids:
        eligible.pop(key, None)
    # Resolve the dependency graph, rejecting cycles and propagating invalidity.
    checked = {}
    pending = dict(eligible)
    while pending:
        progress = False
        for key, item in list(pending.items()):
            if any(reference in pending for reference in item.input_evidence_ids):
                continue
            problem = derived_problem(item, checked)
            if problem:
                gaps.append(f"{key}: {problem}")
            else:
                checked[key] = item
            pending.pop(key)
            progress = True
        if not progress:
            gaps.extend(f"{key}: cyclic derived evidence" for key in pending)
            break
    eligible = checked
    lines = [
        f"# {label(request.symbol)} 研究报告",
        "",
        f"研究日期：{request.as_of_date.isoformat()}；资料截止（排他）：{cutoff.isoformat()}",
        "",
        "校验范围仅限结构化证据引用、时间、单位、期间及数值运算；不代表预测有效或独立审计。",
        "",
        "## 结构化数值",
    ]
    claim_ids = set()
    accepted_claims = 0
    for claim in request.claims:
        problem = claim_problem(claim, eligible)
        if claim.claim_id in claim_ids:
            problem = "duplicate claim identity"
        claim_ids.add(claim.claim_id)
        if problem:
            gaps.append(f"{claim.claim_id}: {problem}")
            continue
        accepted_claims += 1
        refs = ", ".join(label(key) for key in claim.evidence_ids)
        lines.append(
            f"- {label(metric_label(claim.metric))}：{claim.value} {label(claim.unit)}；"
            f"期间 {claim.period_start or '时点'} → {claim.period_end or '未知'}；"
            f"公式 {claim.formula}/1，保留 {claim.decimal_places} 位小数（五取偶）；证据 [{refs}]。"
        )
    if not accepted_claims:
        lines.append("无通过校验的数值论断。")
        gaps.append("no validated numerical claims")
    lines += ["", "## 显式阈值"]
    threshold_ids = set()
    for threshold in request.thresholds:
        problem = threshold_problem(threshold, eligible)
        if threshold.threshold_id in threshold_ids:
            problem = "duplicate threshold identity"
        threshold_ids.add(threshold.threshold_id)
        if problem:
            gaps.append(f"{threshold.threshold_id}: {problem}")
            continue
        observed = eligible[threshold.observed_evidence_id]
        value = Decimal(observed.value)
        classification = "within"
        if threshold.lower is not None and value < Decimal(threshold.lower):
            classification = "below"
        if threshold.upper is not None and value > Decimal(threshold.upper):
            classification = "above"
        classification_label = {"within": "区间内", "below": "低于下界", "above": "高于上界"}[
            classification
        ]
        basis = {"guidance": "公司指引", "historical": "历史参考", "hypothesis": "研究假设"}[
            threshold.basis
        ]
        lines.append(
            f"- {label(metric_label(threshold.metric))}（{basis}）："
            f"[{threshold.lower or '-∞'}, {threshold.upper or '+∞'}] {label(threshold.unit)}；"
            f"观察值 {observed.value}：{classification_label} ({classification})；"
            f"期间 {threshold.period_start or '时点'} → {threshold.period_end}；"
            f"证据 [{label(threshold.observed_evidence_id)}, "
            f"{', '.join(label(key) for key in threshold.evidence_ids)}]。"
        )
        if threshold.rationale:
            lines.append(f"  研究理由（未核实）：{label(threshold.rationale)}")
    if not request.thresholds:
        lines.append("未设置阈值。")
    if request.narrative.strip():
        lines += ["", "## 模型推论，未经事实校验", "", label(request.narrative)]
        if _NUMERIC_OR_THRESHOLD.search(request.narrative):
            gaps.append(
                "unverified numeric or threshold assertion in narrative; "
                "use structured claims/thresholds"
            )
    if request.comparison.strip():
        lines += [
            "",
            "## 较上次的变化（模型对比，未经事实校验）",
            "",
            "\n".join(label(line) for line in request.comparison.split("\n")),
        ]
        if _NUMERIC_OR_THRESHOLD.search(request.comparison):
            gaps.append(
                "unverified numeric or threshold assertion in comparison; "
                "use structured claims/thresholds"
            )
    gaps = list(dict.fromkeys(gaps))
    status = "insufficient_evidence" if gaps else "validated"
    lines += ["", "## 校验状态与资料缺口", "", f"状态：{'证据不足' if gaps else '结构化校验通过'}"]
    lines += [f"- {label(limitation_label(gap))}" for gap in gaps] if gaps else ["结构化检查通过。"]
    lines += ["", "## 完整来源附录（含未核实及未采用资料）", ""]
    for item in evidence.values():
        availability = item.published_at or item.publication_date or "未知"
        eligibility = "可用于结构化校验" if item.evidence_id in eligible else "未核实或未采用"
        lines += [
            f"### [{label(item.evidence_id)}] {label(item.title)}",
            "",
            f"- 来源编号：{label(item.source_id)}；{eligibility}。",
            f"- 原始地址：{label(item.url or '未提供')}。",
            f"- 公开时间：{availability}；采集时间：{item.retrieved_at}。",
        ]
        if item.period_end:
            lines.append(f"- 期间：{item.period_start or '时点'} → {item.period_end}。")
        if item.available_by_date:
            lines.append(
                f"- 可确认可用日期上界：{item.available_by_date}（纽约完整日期）；"
                "仅证明该日结束前可取得此版本，不代表实际公开日期。"
            )
        if item.value is not None:
            lines.append(
                f"- 指标：{label(metric_label(item.metric or '未命名'))}；"
                f"值：{item.value} {label(item.unit or '')}。"
            )
        if item.locator:
            lines.append(f"- 原文定位：{label(item.locator)}。")
        if item.accession:
            lines.append(
                f"- 申报编号：{label(item.accession)}；表单：{label(item.form or '未提供')}。"
            )
        if item.taxonomy or item.tag:
            lines.append(f"- 财务概念：{label(item.taxonomy or '')} / {label(item.tag or '')}。")
        if item.fiscal_year or item.fiscal_period:
            lines.append(
                f"- 申报财年/财季：{item.fiscal_year or '未知'} / "
                f"{label(item.fiscal_period or '未知')}。"
            )
        if item.currency:
            lines.append(f"- 币种：{label(item.currency)}。")
        if item.text:
            lines.append(f"- 原文摘录：{label(item.text)}")
        if item.formula:
            lines.append(
                f"- 派生公式：{label(item.formula)}；"
                f"操作数：{', '.join(label(key) for key in item.input_evidence_ids)}。"
            )
        if item.supersedes_evidence_id:
            lines.append(f"- 替代证据：{label(item.supersedes_evidence_id)}。")
        if item.uncertainty_reason:
            lines.append(f"- 资料限制：{label(limitation_label(item.uncertainty_reason))}")
        lines.append("")
    # A repeated URL or a repeated upstream document identity denotes one source.
    source_groups = []
    for item in eligible.values():
        identities = {"id:" + item.source_id, "url:" + (item.url or item.source_id)}
        overlapping = [group for group in source_groups if group & identities]
        for group in overlapping:
            identities.update(group)
            source_groups.remove(group)
        source_groups.append(identities)
    output = ResearchReportOutput(
        name=f"{request.symbol} 研究报告 {request.as_of_date.isoformat()}",
        content="\n".join(lines),
        status=status,
        data_gaps=gaps,
        evidence=list(evidence.values()),
        narrative_status=(
            "unverified" if request.narrative.strip() or request.comparison.strip() else "absent"
        ),
        independent_source_count=len(source_groups),
        cutoff_at=cutoff,
    )
    return project(output.model_dump(mode="json", by_alias=True, exclude_none=True))
