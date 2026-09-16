"""Reader-facing labels for Finance research facts and collection limitations."""

import re

METRICS = {
    "revenue": "收入",
    "gross_profit": "毛利润",
    "grossMargin": "毛利率",
    "operating_income": "营业利润",
    "net_income": "净利润",
    "operating_cash_flow": "经营现金流",
    "capital_expenditures": "资本开支",
    "productive_asset_expenditures": "生产性资产支出（含软件及其他无形资产）",
    "free_cash_flow": "自由现金流",
    "cash": "现金及现金等价物",
    "short_term_debt": "短期债务",
    "long_term_debt_current": "一年内到期的长期债务",
    "long_term_debt_noncurrent": "非流动长期债务",
    "total_debt": "债务合计",
    "shares_outstanding": "实际发行在外股数",
    "weighted_average_shares": "加权平均基本股数",
    "diluted_weighted_average_shares": "加权平均稀释股数",
    "eps_basic": "基本每股收益",
    "eps_diluted": "稀释每股收益",
    "net_margin_percent": "净利率",
    "market.close": "收盘价",
    "market_cap_estimate": "估算市值",
    "enterprise_value_estimate": "估算企业价值",
}

LIMITATIONS = {
    "sec_symbol_cik_mismatch": "证券代码与监管标识不对应，已拒绝采用其他发行人的原文。",
    "invalid structured item": "模型提供的结构化论断或阈值格式不合法，已排除该条目。",
    "sec_filings_truncated": "SEC 申报列表达到本次采集上限，覆盖不完整。",
    "document_size_limit": "原始文档超过本次读取大小上限，正文可能不完整。",
    "metric_missing": "截止时间前未取得该指标的可用标准财务事实。",
    "calculation_gap": "缺少唯一、口径相容的计算输入，未生成该派生值。",
    "unsupported_unit": "来源单位不受支持，相关数值未参与计算。",
    "ambiguous_concept": "同一期间存在多个财务概念，未擅自择一替代。",
    "coverage_limit": "仅覆盖本次可取得的申报及标准财务概念，资料不保证完整。",
    "output_bounded": "资料达到本次输出上限，较早期间未全部展示。",
    "source_unavailable": "资料来源暂时不可用。",
    "fundamentals_unavailable": "SEC 财务资料暂时不可用。",
    "SEC financials unavailable": "SEC 财务资料暂时不可用。",
    "no validated numerical claims": "没有通过校验的结构化数值论断。",
    "unverified numeric or threshold assertion in narrative": (
        "模型解释包含尚未通过结构化校验的数字或阈值判断。"
    ),
    "unverified numeric or threshold assertion in comparison": (
        "模型对比包含尚未通过结构化校验的数字或阈值判断。"
    ),
    "unverified source": "来源尚未核实，未纳入已验证事实。",
    "missing original URL or locator": "缺少原始地址或原文定位，无法核对出处。",
    "published outside cutoff": "公开时间超出研究截止，未用于本次判断。",
    "publication later than retrieval": "公开时间与采集时间矛盾，未采用该证据。",
    "date-only publication cannot establish intraday availability": (
        "来源只有公开日期，无法证明在当日截止时刻前已经可得。"
    ),
    "publication time unknown": "公开时间未知，无法确认截止前可得性。",
    "known availability upper bound exceeds cutoff": (
        "已知可用日期的上界晚于研究截止，无法确认截止前可得性。"
    ),
    "publication unknown or outside cutoff": "公开时间未知或超出截止，未纳入研究。",
    "evidence symbol differs": "资料对应的证券与研究对象不同。",
    "symbol mismatch": "资料对应的证券与研究对象不同。",
    "conflicting duplicate evidence identity": "相同证据编号对应不同内容，未采用冲突记录。",
    "conflicting evidence identity excluded": "相同证据编号对应不同内容，已排除冲突记录。",
    "missing or ineligible derived operand": "派生计算引用的原始证据缺失或不符合使用条件。",
    "cyclic derived evidence": "派生证据存在循环引用，无法复算。",
    "missing or ineligible evidence reference": "论断引用的证据缺失或不符合使用条件。",
    "inference or user claim is not a verified fact": "模型推论或用户材料不能当作已核实事实。",
    "repeated operand reference": "计算重复引用同一操作数，未通过校验。",
    "non-numeric operand": "计算引用的证据没有可复算数值。",
    "period mismatch": "论断与证据的期间不一致。",
    "operand unit or currency mismatch": "计算输入的单位或币种不一致。",
    "result unit mismatch": "计算结果的单位与公式不一致。",
    "identity metric mismatch": "直接引用的指标与原始证据不一致。",
    "value does not match recomputation": "论断数值与按所列公式复算的结果不一致。",
    "invalid calculation or zero denominator": "计算不成立或分母为零，未生成结果。",
    "missing or ineligible observed evidence": "阈值比较缺少可用的实际观察值。",
    "observation metric, unit or period mismatch": "实际观察值与阈值的指标、单位或期间不一致。",
    "missing or ineligible threshold source": "阈值没有可核验的来源证据。",
    "threshold source metric, unit or period mismatch": "阈值来源与声明的指标、单位或期间不一致。",
    "bounds do not match center plus/minus tolerance": "阈值上下界不等于原指引中心值加减容差。",
    "threshold bounds are not supported by cited values": "引用证据不能支持所声明的阈值边界。",
    "duplicate claim identity": "论断编号重复，未采用重复论断。",
    "duplicate threshold identity": "阈值编号重复，未采用重复阈值。",
    "SEC filing focus fy/fp retained": (
        "财年、财季沿用申报标签；实际期间按起止日期识别。" "摘录来自 XBRL 数据，不代表已阅读全文。"
    ),
    "Superseded fact": "该事实已被后续申报修订，仅保留作出处核对。",
    "Evidence truncated to": "证据达到本次数量上限，资料覆盖不完整。",
    "Additional collection gaps omitted": "资料限制过多，仅展示本次上限内的项目。",
    "Selected prediction collection failed": "所选预测市场资料采集失败，增强信号不可用。",
    "No completed daily bars": "研究截止前未取得已完成的日行情。",
    "News item without an original URL": "新闻缺少原始地址，已排除。",
}


def metric_label(metric: str) -> str:
    return METRICS.get(metric, metric)


def limitation_label(message: str) -> str:
    matches = [text for key, text in LIMITATIONS.items() if key in message]
    if matches:
        subjects = [metric_label(metric) for metric in re.findall(r"\[([a-z_.]+)\]", message)]
        prefix = "、".join(subjects) + "：" if subjects else ""
        return prefix + " ".join(dict.fromkeys(matches))
    if any(
        marker in message.lower()
        for marker in ("traceback", "authorization", "request headers", "stack trace")
    ):
        return "资料来源返回处理错误，相关资料未纳入判断。"
    return "来源返回资料限制：" + message
