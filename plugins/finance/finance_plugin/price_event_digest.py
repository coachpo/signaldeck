"""Chinese Markdown digest of a K-line event scan for people reading a run or a report."""

from collections.abc import Sequence
from decimal import Decimal

from .price_event_contracts import (
    PriceEvent,
    PriceEventDetector,
    PriceEventMeasure,
    PriceEventsLookupResult,
)
from .price_series import quantize

TWO_PLACES = Decimal("0.01")
WARNING_LIMIT = 20
RULE_NAMES = {
    "new_high_low": "收盘新高/新低",
    "near_high_low": "逼近高低点",
    "drawdown": "回撤/反弹",
    "breakout": "突破",
    "failed_breakout": "假突破",
    "gap": "跳空缺口",
    "large_move": "单日大幅涨跌",
    "window_move": "多日急涨急跌",
    "spike_reversal": "大幅涨跌被回吐",
    "gap_fill": "缺口回补",
    "island_reversal": "岛形反转",
    "ma_cross": "均线交叉",
    "price_ma_cross": "价格穿越均线",
    "macd_cross": "MACD 交叉",
    "rsi_threshold": "RSI 超买超卖",
    "bollinger_break": "布林带突破",
    "bollinger_squeeze": "布林带收口",
    "range_contraction": "窄幅整理",
    "inside_bar": "内包线",
    "engulfing": "吞没形态",
    "pin_bar": "锤子线/射击之星",
    "volume_spike": "放量",
    "streak": "连涨连跌",
    "relative_strength": "相对强弱",
}
DIRECTIONS = {"up": "向上", "down": "向下", "neutral": "中性"}
MEASURE_NAMES = {
    "breakPercent": "突破幅度",
    "sessionsSinceLevel": "极值距今",
    "levelDistancePercent": "距参考价",
    "intradayBreakPercent": "盘中越过",
    "volumeRatio": "量比",
    "gapPercent": "缺口",
    "gapAtr": "缺口折合",
    "thresholdPercent": "阈值",
    "moveAtr": "涨跌折合",
    "returnZScore": "收益 z 值",
    "windowReturnPercent": "区间涨跌",
    "moveSigma": "涨跌折合",
    "spikePercent": "原涨跌幅",
    "sessionsToReverse": "回吐用时",
    "sessionsToFill": "回补用时",
    "islandSessions": "岛形长度",
    "fastAverage": "快线",
    "slowAverage": "慢线",
    "averageDistancePercent": "距均线",
    "macd": "MACD",
    "macdSignal": "信号线",
    "macdHistogram": "柱值",
    "rsi": "RSI",
    "bandwidthPercent": "带宽",
    "referenceBandwidthPercent": "参考带宽",
    "rangePercent": "振幅",
    "bodyRatio": "实体比",
    "shadowRatio": "影线占比",
    "trendChangePercent": "此前涨跌",
    "volume": "成交量",
    "averageVolume": "均量",
    "streakLength": "连续天数",
    "streakChangePercent": "连续涨跌",
    "stockReturnPercent": "个股涨跌",
    "benchmarkReturnPercent": "基准涨跌",
    "excessReturnPercent": "超额涨跌",
}


def render_digest(result: PriceEventsLookupResult, detectors: Sequence[PriceEventDetector]) -> str:
    as_of = result.as_of_date.isoformat()
    listed = [item for item in result.series if item.events]
    lines = [f"# K 线事件 · {as_of}", ""]
    if result.latest_session is None:
        lines.append(f"扫描 {len(result.scanned_symbols)} 只证券，没有可用的已完成交易日。")
    else:
        found = (
            f"{len(listed)} 只证券共 {result.matched_count} 个事件"
            if result.matched_count
            else "未发现所选事件"
        )
        lines.append(
            f"扫描 {len(result.scanned_symbols)} 只证券，最新完成交易日 "
            f"{result.latest_session.isoformat()}；{found}。"
        )
        if result.latest_session != result.as_of_date:
            lines.append(f"{as_of} 没有已完成的交易日：当天休市或尚未收盘。")
    if listed:
        lines += [
            "",
            "| 证券 | 交易日 | 事件 | 方向 | 收盘 | 涨跌幅 | 要点 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in listed:
            for event in item.events:
                change = "—" if event.change_percent is None else _signed(event.change_percent)
                cells = [
                    item.symbol,
                    event.session.isoformat(),
                    RULE_NAMES[event.detector.type],
                    DIRECTIONS[event.direction],
                    _fixed(event.raw_close),
                    change,
                    _details(event),
                ]
                lines.append("| " + " | ".join(cells) + " |")
        omitted = [
            f"{item.symbol} 另有 {item.event_count - len(item.events)} 个较早的事件未列出。"
            for item in listed
            if item.event_count > len(item.events)
        ]
        if omitted:
            lines += ["", *omitted]
    lines += [
        "",
        "规则：" + "；".join(detector.label() for detector in detectors),
        "",
        "按分红复权价格识别事件（缺少复权数据的证券见提示）；收盘列是 provider 原始收盘价，"
        "涨跌幅按识别所用的价格计算。",
    ]
    if result.warnings:
        lines += ["", "提示："]
        lines += [f"- {warning.message}" for warning in result.warnings[:WARNING_LIMIT]]
        if len(result.warnings) > WARNING_LIMIT:
            lines.append(f"- 另有 {len(result.warnings) - WARNING_LIMIT} 条提示未列出。")
    lines += ["", "事件只描述历史价格，不构成预测或交易建议。"]
    return "\n".join(lines)


def _details(event: PriceEvent) -> str:
    parts = [f"{MEASURE_NAMES[item.name]} {_measure(item)}" for item in event.measures]
    if event.level is not None:
        parts.insert(0, f"参考价 {_fixed(event.level)}")
    return "，".join(parts)


def _measure(measure: PriceEventMeasure) -> str:
    unit = measure.unit
    if unit in {"sessions", "shares"}:
        return f"{measure.value} {'个交易日' if unit == 'sessions' else '股'}"
    suffix = {"percent": "%", "atr": " ATR", "sigma": "σ"}.get(unit, "")
    return _fixed(measure.value) + suffix


def _fixed(value: Decimal) -> str:
    return format(quantize(value, TWO_PLACES), "f")


def _signed(value: Decimal) -> str:
    return format(quantize(value, TWO_PLACES), "+f") + "%"
