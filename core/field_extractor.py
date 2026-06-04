"""Semantic + spatial field extraction from OCR layout (no fixed coordinates)."""

from __future__ import annotations

import re
from typing import Callable

from core.field_definitions import (
    FIELD_SPECS,
    RE_DATE,
    RE_DATE_LOOSE,
    RE_INVOICE_NUMBER,
    RE_MONEY,
    RE_TAX_ID,
    RE_TAX_RATE,
    FieldSpec,
    SpatialStrategy,
    label_matches,
    normalize_label,
)
from core.layout_analyzer import (
    LayoutDocument,
    _median_line_height,
    blocks_between_anchors,
    build_layout,
)
from core.models import InvoiceLineItem, InvoiceRecord, OcrBlock

def _parse_date(text: str) -> str | None:
    for m in RE_DATE.finditer(text):
        g = m.groups()
        if g[0]:
            y, mo, d = g[0], g[1], g[2]
        else:
            y, mo, d = g[3], g[4], g[5]
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = RE_DATE_LOOSE.search(text)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return None


def _parse_money(text: str) -> float | None:
    m = RE_MONEY.match(text.strip())
    if not m:
        # bare number
        cleaned = text.replace(",", "").replace("¥", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _money_close(left: float | None, right: float | None, tolerance: float = 0.02) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) <= tolerance


def _clean_tax_id(text: str) -> str | None:
    t = re.sub(r"[\s:：]", "", text).upper()
    m = re.search(r"[A-Z0-9]{15,20}", t)
    if m:
        return m.group(0)
    return None


def _horizontal_gap(anchor: OcrBlock, candidate: OcrBlock) -> float:
    _, _, axmax, _ = anchor.bbox
    cxmin, _, _, _ = candidate.bbox
    return cxmin - axmax


def _vertical_gap(anchor: OcrBlock, candidate: OcrBlock) -> float:
    _, _, _, aymax = anchor.bbox
    _, cymin, _, _ = candidate.bbox
    return cymin - aymax


def _same_row(anchor: OcrBlock, candidate: OcrBlock, tol_ratio: float = 0.5) -> bool:
    ah = anchor.bbox[3] - anchor.bbox[1]
    tol = max(ah * tol_ratio, 8.0)
    return abs(anchor.mid_y - candidate.mid_y) <= tol and candidate.page_index == anchor.page_index


def find_anchor_blocks(layout: LayoutDocument, aliases: tuple[str, ...]) -> list[OcrBlock]:
    return [b for b in layout.blocks if label_matches(b.text, aliases)]


def value_right_same_row(anchor: OcrBlock, candidates: list[OcrBlock]) -> list[OcrBlock]:
    out = []
    for c in candidates:
        if c is anchor:
            continue
        if not _same_row(anchor, c):
            continue
        if _horizontal_gap(anchor, c) > -5:  # to the right or slight overlap
            out.append(c)
    return sorted(out, key=lambda b: _horizontal_gap(anchor, b))


def value_below(anchor: OcrBlock, candidates: list[OcrBlock], max_gap_ratio: float = 2.5) -> list[OcrBlock]:
    ah = anchor.bbox[3] - anchor.bbox[1]
    max_gap = ah * max_gap_ratio
    out = []
    for c in candidates:
        if c is anchor or c.page_index != anchor.page_index:
            continue
        vgap = _vertical_gap(anchor, c)
        if 0 <= vgap <= max_gap:
            out.append(c)
    return sorted(out, key=lambda b: (_vertical_gap(anchor, b), b.mid_x))


def apply_spatial_rule(
    anchor: OcrBlock,
    candidates: list[OcrBlock],
    strategy: SpatialStrategy,
) -> list[OcrBlock]:
    if strategy == SpatialStrategy.RIGHT_SAME_ROW:
        return value_right_same_row(anchor, candidates)
    if strategy == SpatialStrategy.BELOW:
        return value_below(anchor, candidates)
    if strategy == SpatialStrategy.RIGHT_OR_BELOW:
        right = value_right_same_row(anchor, candidates)
        return right if right else value_below(anchor, candidates)
    return candidates


def validate_value(text: str, spec: FieldSpec) -> bool:
    if spec.value_pattern:
        return bool(spec.value_pattern.search(text.strip()))
    return bool(text.strip())


def normalize_field_value(text: str, spec: FieldSpec) -> str:
    t = text.strip()
    if spec.normalize == "date":
        d = _parse_date(t)
        return d or t
    if spec.normalize == "money":
        v = _parse_money(t)
        return str(v) if v is not None else t
    if spec.normalize == "tax_id":
        tid = _clean_tax_id(t)
        return tid or t
    if spec.normalize == "percent":
        m = RE_TAX_RATE.search(t)
        return m.group(0) if m else t
    return t


def _extract_from_anchors(
    layout: LayoutDocument,
    spec: FieldSpec,
    candidates: list[OcrBlock] | None = None,
) -> str | None:
    pool = candidates if candidates is not None else layout.blocks
    anchors = find_anchor_blocks(layout, spec.label_aliases)
    for anchor in anchors:
        nearby = apply_spatial_rule(anchor, pool, spec.strategy)
        for block in nearby:
            val = block.text.strip()
            if label_matches(val, spec.label_aliases):
                continue
            if spec.value_pattern and not spec.value_pattern.search(val):
                # try concatenating same-row neighbors
                row_vals = value_right_same_row(anchor, pool)
                combined = "".join(b.text for b in row_vals)
                if spec.value_pattern.search(combined):
                    val = combined
                else:
                    continue
            if validate_value(val, spec):
                return normalize_field_value(val, spec)
    return None


def _extract_invoice_type(layout: LayoutDocument) -> str:
    text = layout.full_text.replace(" ", "")
    return "专用发票" if "专用" in text else "普通发票"


def _extract_invoice_number(layout: LayoutDocument) -> str:
    spec = next(s for s in FIELD_SPECS if s.key == "invoice_number")
    val = _extract_from_anchors(layout, spec)
    if val and RE_INVOICE_NUMBER.match(re.sub(r"\s", "", val)):
        return re.sub(r"\s", "", val)

    # full-text fallback: label context
    for anchor in find_anchor_blocks(layout, spec.label_aliases):
        for c in apply_spatial_rule(anchor, layout.blocks, SpatialStrategy.RIGHT_OR_BELOW):
            digits = re.sub(r"\D", "", c.text)
            if RE_INVOICE_NUMBER.match(digits):
                return digits

    full = layout.full_text.replace(" ", "")
    m = re.search(r"发票号码[：:]*?(\d{8,30})", full)
    if m:
        return m.group(1)
    m = re.search(r"(?<![\d])(\d{20})(?![\d])", full)
    if m:
        return m.group(1)
    m = re.search(r"(?<![\d])(\d{8,12})(?![\d])", full)
    return m.group(1) if m else ""


def _extract_issue_date(layout: LayoutDocument) -> str:
    spec = next(s for s in FIELD_SPECS if s.key == "issue_date")
    val = _extract_from_anchors(layout, spec)
    if val:
        d = _parse_date(val)
        if d:
            return d

    for line in layout.lines:
        if "开票日期" in line.text or "日期" in line.text:
            d = _parse_date(line.text)
            if d:
                return d

    d = _parse_date(layout.full_text)
    return d or ""


def _seller_side_blocks(layout: LayoutDocument, page_index: int = 0) -> list[OcrBlock]:
    """Blocks on the seller column (right of 「销售方」 anchor x)."""
    anchors = [
        b
        for b in layout.blocks
        if b.page_index == page_index and "销售方" in b.text.replace(" ", "")
    ]
    if not anchors:
        return layout.blocks_on_page(page_index)
    split_x = max(b.mid_x for b in anchors)
    return [b for b in layout.blocks_on_page(page_index) if b.mid_x >= split_x - 20]


def _extract_seller_region(layout: LayoutDocument) -> list[OcrBlock]:
    side = _seller_side_blocks(layout)
    if len(side) >= 2:
        return side
    region = blocks_between_anchors(layout, "销售方", "购买方")
    if len(region) < 2:
        region = blocks_between_anchors(layout, "销方", "购方")
    return region


def _parse_dual_name_line(text: str) -> str | None:
    """双栏发票：两个「名称：」时取后者为销售方。"""
    parts = re.findall(r"名称[：:]\s*([^名称下载]+?)(?=\s*名称|下载|$)", text)
    if len(parts) >= 2:
        return parts[1].strip()
    return None


def _extract_seller_name(layout: LayoutDocument) -> str:
    for line in layout.lines:
        dual = _parse_dual_name_line(line.text)
        if dual and len(dual) >= 2:
            return dual

    region = _extract_seller_region(layout)
    name_blocks = []
    for b in region:
        t = b.text.strip()
        if any(k in t for k in ("发票号码", "开票日期", "下载次数")):
            continue
        if label_matches(t, ("销售方", "销方", "购买方", "购方")):
            continue
        if label_matches(t, ("名称", "纳税人识别号", "统一社会信用代码")) and "：" not in t:
            continue
        if RE_TAX_ID.match(re.sub(r"\s", "", t)) and not re.search(r"[A-Z]", t, re.I):
            continue
        if "名称" in t and "：" in t:
            m = re.search(r"名称[：:]\s*(.+)", t)
            if m:
                t = m.group(1).strip()
        if len(t) >= 2 and not re.match(r"^[\d¥%.]+$", t):
            name_blocks.append((b.bbox[1], b.mid_x, t))

    if name_blocks:
        texts = [x[2] for x in name_blocks]
        return max(texts, key=len)

    val = _extract_from_anchors(layout, next(s for s in FIELD_SPECS if s.key == "seller_name"), region)
    return val or ""


_NEXT_COLUMN_MARKERS = ("规格型号", "单位", "数量", "单价", "金额", "税率", "税额", "征收率")
_TABLE_END_MARKERS = ("合计", "价税合计", "小计", "总计", "价税合计(小写)")


def _is_project_name_header_block(block: OcrBlock) -> bool:
    t = block.text.replace(" ", "")
    if "项目名称" not in t:
        return False
    if any(k in t for k in ("销售方", "购买方", "纳税人识别号")):
        return False
    return True


def _is_project_name_text(text: str, *, allow_single_char: bool = False) -> bool:
    """Keep 项目名称 text while allowing OCR-split continuation fragments."""
    t = text.strip()
    min_len = 1 if allow_single_char else 2
    if len(t) < min_len:
        return False
    if t in ("计", "合计", "小计", "总计"):
        return False
    if "项目名称" in t.replace(" ", ""):
        return False
    if any(m in t for m in _TABLE_END_MARKERS):
        return False
    if re.match(r"^[\d¥￥%,.\s\-—]+$", t):
        return False
    if RE_TAX_ID.match(re.sub(r"\s", "", t)):
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?[%％]?", t):
        return False
    if label_matches(t, _NEXT_COLUMN_MARKERS) and len(t) <= 8:
        return False
    return True


def _is_project_name_cell(text: str) -> bool:
    """Keep full 项目名称 cell text including * prefixes."""
    return _is_project_name_text(text)


def _is_project_name_continuation(text: str) -> bool:
    return _is_project_name_text(text, allow_single_char=True)


def _extract_tax_items(layout: LayoutDocument) -> str:
    """Extract complete values from the 项目名称 column only."""
    page = 0
    page_blocks = layout.blocks_on_page(page)
    headers = [b for b in page_blocks if _is_project_name_header_block(b)]
    if not headers:
        return ""

    # Prefer the dedicated「项目名称」header cell (short label block).
    header = min(headers, key=lambda b: (len(b.text), b.bbox[1]))
    header_top = header.bbox[1]
    row_tol = max(_median_line_height(page_blocks) * 0.55, 6.0)

    col_xmin = header.bbox[0] - 10
    col_xmax = header.bbox[2] + max((header.bbox[2] - header.bbox[0]) * 6, 120)

    for b in page_blocks:
        if abs(b.mid_y - header.mid_y) > row_tol * 1.5:
            continue
        if b.bbox[0] <= header.bbox[2]:
            continue
        bt = b.text.replace(" ", "")
        if any(m in bt for m in _NEXT_COLUMN_MARKERS):
            col_xmax = min(col_xmax, b.bbox[0] - 4)

    y_end = layout.page_heights.get(page, 1000.0) * 0.75
    for b in sorted(page_blocks, key=lambda x: x.bbox[1]):
        if b.bbox[1] < header_top + row_tol:
            continue
        bt = b.text.strip()
        if bt in ("计", "合计", "小计") or any(m in bt for m in _TABLE_END_MARKERS):
            y_end = min(y_end, b.bbox[1])
            break

    data_lefts = [
        b.bbox[0]
        for b in page_blocks
        if b.bbox[1] >= header_top + row_tol * 0.5
        and b.bbox[1] < y_end
        and b.bbox[0] < col_xmax
        and _is_project_name_cell(b.text.strip())
    ]
    if data_lefts:
        col_xmin = max(0.0, min(col_xmin, min(data_lefts) - 4))

    rows: dict[int, list[OcrBlock]] = {}
    for b in page_blocks:
        if normalize_label(b.text) == normalize_label("项目名称"):
            continue
        if b.bbox[1] < header_top + row_tol * 0.5:
            continue
        if b.bbox[1] >= y_end:
            continue
        if b.mid_x < col_xmin or b.mid_x > col_xmax:
            continue
        row_key = int(round(b.mid_y / row_tol))
        rows.setdefault(row_key, []).append(b)

    items: list[str] = []
    seen: set[str] = set()
    for row_key in sorted(rows.keys()):
        row_blocks = sorted(rows[row_key], key=lambda bl: bl.mid_x)
        text = "".join(x.text for x in row_blocks).strip()
        row_mid = sum(b.mid_y for b in row_blocks) / len(row_blocks)
        same_row_value_blocks = [
            b
            for b in page_blocks
            if b.page_index == page
            and abs(b.mid_y - row_mid) <= row_tol
            and b.mid_x > col_xmax + 4
            and b.bbox[1] < y_end
            and not label_matches(b.text.strip(), _NEXT_COLUMN_MARKERS)
            and not any(m in b.text.strip() for m in _TABLE_END_MARKERS)
        ]
        has_same_row_values = bool(same_row_value_blocks)
        if not _is_project_name_cell(text):
            if items and not has_same_row_values and _is_project_name_continuation(text):
                items[-1] = f"{items[-1]}{text}"
                seen.add(items[-1])
            continue
        if items and not has_same_row_values:
            items[-1] = f"{items[-1]}{text}"
            seen.add(items[-1])
            continue
        if text in seen:
            continue
        seen.add(text)
        items.append(text)

    return "；".join(items)


def _line_item_from_row(name: str, value_blocks: list[OcrBlock]) -> InvoiceLineItem:
    sorted_values = sorted(value_blocks, key=lambda b: b.mid_x)
    rate_block = next((b for b in sorted_values if RE_TAX_RATE.search(b.text)), None)
    tax_rate = ""
    quantity = ""
    amount: float | None = None
    tax_amount: float | None = None

    if rate_block:
        m = RE_TAX_RATE.search(rate_block.text)
        tax_rate = m.group(0) if m else rate_block.text.strip()
        before_rate = [b for b in sorted_values if b.mid_x < rate_block.mid_x]
        after_rate = [b for b in sorted_values if b.mid_x > rate_block.mid_x]

        money_before_rate = [
            (b, parsed)
            for b in before_rate
            if (parsed := _parse_money(b.text)) is not None
        ]
        if money_before_rate:
            _, amount = money_before_rate[-1]
            prior_money = money_before_rate[:-1]
            if len(prior_money) >= 2:
                quantity = prior_money[0][0].text.strip()
            elif len(prior_money) == 1:
                unit_price = prior_money[0][1]
                quantity = "1" if _money_close(unit_price, amount) else ""
        for b in after_rate:
            tax_amount = _parse_money(b.text)
            if tax_amount is not None:
                break
    else:
        money_values = [_parse_money(b.text) for b in sorted_values]
        money_values = [v for v in money_values if v is not None]
        if money_values:
            amount = money_values[-2] if len(money_values) >= 2 else money_values[-1]
            tax_amount = money_values[-1] if len(money_values) >= 2 else None
            for b in sorted_values:
                if _parse_money(b.text) is not None:
                    quantity = b.text.strip()
                    break

    return InvoiceLineItem(
        name=name,
        quantity=quantity,
        amount=amount,
        tax_amount=tax_amount,
        tax_rate=tax_rate,
    )


def _extract_line_items(layout: LayoutDocument) -> list[InvoiceLineItem]:
    """Extract item-level rows with row-specific amount/tax fields."""
    page = 0
    page_blocks = layout.blocks_on_page(page)
    headers = [b for b in page_blocks if _is_project_name_header_block(b)]
    if not headers:
        return []

    header = min(headers, key=lambda b: (len(b.text), b.bbox[1]))
    header_top = header.bbox[1]
    row_tol = max(_median_line_height(page_blocks) * 0.55, 6.0)

    col_xmin = header.bbox[0] - 10
    col_xmax = header.bbox[2] + max((header.bbox[2] - header.bbox[0]) * 6, 120)
    for b in page_blocks:
        if abs(b.mid_y - header.mid_y) > row_tol * 1.5:
            continue
        if b.bbox[0] <= header.bbox[2]:
            continue
        bt = b.text.replace(" ", "")
        if any(m in bt for m in _NEXT_COLUMN_MARKERS):
            col_xmax = min(col_xmax, b.bbox[0] - 4)

    y_end = layout.page_heights.get(page, 1000.0) * 0.75
    for b in sorted(page_blocks, key=lambda x: x.bbox[1]):
        if b.bbox[1] < header_top + row_tol:
            continue
        bt = b.text.strip()
        if bt in ("计", "合计", "小计") or any(m in bt for m in _TABLE_END_MARKERS):
            y_end = min(y_end, b.bbox[1])
            break

    data_lefts = [
        b.bbox[0]
        for b in page_blocks
        if b.bbox[1] >= header_top + row_tol * 0.5
        and b.bbox[1] < y_end
        and b.bbox[0] < col_xmax
        and _is_project_name_cell(b.text.strip())
    ]
    if data_lefts:
        col_xmin = max(0.0, min(col_xmin, min(data_lefts) - 4))

    rows: dict[int, list[OcrBlock]] = {}
    for b in page_blocks:
        if normalize_label(b.text) == normalize_label("项目名称"):
            continue
        if b.bbox[1] < header_top + row_tol * 0.5:
            continue
        if b.bbox[1] >= y_end:
            continue
        if b.mid_x < col_xmin or b.mid_x > col_xmax:
            continue
        row_key = int(round(b.mid_y / row_tol))
        rows.setdefault(row_key, []).append(b)

    line_items: list[InvoiceLineItem] = []
    for row_key in sorted(rows.keys()):
        row_blocks = sorted(rows[row_key], key=lambda bl: bl.mid_x)
        text = "".join(x.text for x in row_blocks).strip()
        row_mid = sum(b.mid_y for b in row_blocks) / len(row_blocks)
        value_blocks = [
            b
            for b in page_blocks
            if b.page_index == page
            and abs(b.mid_y - row_mid) <= row_tol
            and b.mid_x > col_xmax + 4
            and b.bbox[1] < y_end
            and not label_matches(b.text.strip(), _NEXT_COLUMN_MARKERS)
            and not any(m in b.text.strip() for m in _TABLE_END_MARKERS)
        ]
        if not _is_project_name_cell(text):
            if line_items and not value_blocks and _is_project_name_continuation(text):
                line_items[-1].name = f"{line_items[-1].name}{text}"
            continue
        if line_items and not value_blocks:
            line_items[-1].name = f"{line_items[-1].name}{text}"
            continue

        item = _line_item_from_row(text, value_blocks)
        line_items.append(item)

    return line_items


def _extract_from_ji_line(layout: LayoutDocument) -> tuple[float | None, float | None]:
    """「计」行常见格式：计 ￥金额 ￥税额。"""
    for line in layout.lines:
        t = line.text.replace(" ", "")
        if not t.startswith("计") and "计" not in line.text:
            continue
        monies = re.findall(r"[\d,]+\.\d{1,2}", line.text)
        if len(monies) >= 2:
            return _parse_money(monies[0]), _parse_money(monies[1])
    return None, None


def _extract_money_field(layout: LayoutDocument, key: str) -> float | None:
    amt, tax = _extract_from_ji_line(layout)
    if key == "amount" and amt is not None:
        return amt
    if key == "tax_amount" and tax is not None:
        return tax

    spec = next(s for s in FIELD_SPECS if s.key == key)
    anchors = find_anchor_blocks(layout, spec.label_aliases)
    values: list[float] = []

    for anchor in anchors:
        if key == "amount" and "税额" in anchor.text and "合计" not in anchor.text:
            continue
        if key == "tax_amount" and "不含税" in anchor.text:
            continue
        for c in apply_spatial_rule(anchor, layout.blocks, SpatialStrategy.RIGHT_OR_BELOW):
            v = _parse_money(c.text)
            if v is not None:
                values.append(v)

    if values:
        return values[-1]

    for line in layout.lines:
        if "税率" in line.text or "征收率" in line.text:
            nums = re.findall(r"[\d,]+\.\d{1,2}", line.text)
            if key == "amount" and len(nums) >= 1:
                return _parse_money(nums[0])
            if key == "tax_amount" and len(nums) >= 2:
                return _parse_money(nums[-1])

    h = layout.page_heights.get(0, 1000)
    cutoff = h * 0.65
    bottom = sorted(
        [b for b in layout.blocks if b.page_index == 0 and b.bbox[1] >= cutoff],
        key=lambda b: (b.bbox[1], b.mid_x),
    )
    nums: list[float] = []
    for b in bottom:
        v = _parse_money(b.text)
        if v is not None:
            nums.append(v)

    if key == "tax_amount" and len(nums) >= 2:
        return nums[-1]
    if key == "amount" and nums:
        return nums[0] if len(nums) == 1 else nums[-2] if len(nums) >= 2 else nums[-1]
    return None


_COMMON_VAT_RATES = ("17%", "13%", "9%", "6%", "3%", "1%", "0%")


def _extract_tax_rate(layout: LayoutDocument) -> str:
    spec = next(s for s in FIELD_SPECS if s.key == "tax_rate")
    val = _extract_from_anchors(layout, spec)
    if val and _is_plausible_tax_rate(val):
        return val

    for line in layout.lines:
        if "税率" in line.text or "征收率" in line.text or "%" in line.text or "％" in line.text:
            for m in re.finditer(r"(\d{1,2}(?:\.\d+)?)\s*[%％]", line.text):
                pct = float(m.group(1))
                if 0 <= pct <= 17:
                    return f"{m.group(1)}%"
            for rate in _COMMON_VAT_RATES:
                if rate in line.text:
                    return rate
            if "免税" in line.text:
                return "免税"
            if "不征税" in line.text:
                return "不征税"

    for rate in _COMMON_VAT_RATES:
        if rate in layout.full_text:
            return rate

    if "免税" in layout.full_text:
        return "免税"
    return ""


def _is_plausible_tax_rate(val: str) -> bool:
    if val in ("免税", "不征税", "0%", "—", "-"):
        return True
    m = re.match(r"^(\d+(?:\.\d+)?)%$", val.strip())
    if not m:
        return False
    try:
        return 0 <= float(m.group(1)) <= 17
    except ValueError:
        return False


_FIELD_EXTRACTORS: dict[str, Callable[[LayoutDocument], str | float | None]] = {
    "invoice_type": _extract_invoice_type,
    "invoice_number": _extract_invoice_number,
    "issue_date": _extract_issue_date,
    "seller_name": _extract_seller_name,
    "tax_items": _extract_tax_items,
    "amount": lambda lay: _extract_money_field(lay, "amount"),
    "tax_amount": lambda lay: _extract_money_field(lay, "tax_amount"),
    "tax_rate": _extract_tax_rate,
}


REQUIRED_KEYS = (
    "invoice_number",
    "issue_date",
    "seller_name",
)


def extract_fields(blocks: list[OcrBlock], source_file: str) -> InvoiceRecord:
    """Run layout analysis and extract all target fields into InvoiceRecord."""
    layout = build_layout(blocks)
    record = InvoiceRecord(
        source_file=source_file,
        status="success",
        raw_ocr_text=layout.full_text[:8000],
    )

    record.invoice_type = str(_FIELD_EXTRACTORS["invoice_type"](layout) or "")
    record.invoice_number = str(_FIELD_EXTRACTORS["invoice_number"](layout) or "")
    record.issue_date = str(_FIELD_EXTRACTORS["issue_date"](layout) or "")
    record.seller_name = str(_FIELD_EXTRACTORS["seller_name"](layout) or "")
    record.tax_items = str(_FIELD_EXTRACTORS["tax_items"](layout) or "")
    record.line_items = _extract_line_items(layout)
    record.amount = _FIELD_EXTRACTORS["amount"](layout)  # type: ignore[assignment]
    record.tax_amount = _FIELD_EXTRACTORS["tax_amount"](layout)  # type: ignore[assignment]
    record.tax_rate = str(_FIELD_EXTRACTORS["tax_rate"](layout) or "")

    missing = []
    if not record.invoice_number:
        missing.append("发票号码")
    if not record.issue_date:
        missing.append("开票日期")
    if not record.seller_name:
        missing.append("销售方名称")

    if missing:
        record.warnings.append(f"未识别字段: {', '.join(missing)}")
        record.status = "partial" if any(
            getattr(record, k) for k in ("invoice_number", "issue_date", "seller_name", "amount")
        ) else "failed"
    else:
        record.status = "success"

    low_conf = [b for b in blocks if b.score < 0.5]
    if low_conf:
        record.warnings.append(f"存在 {len(low_conf)} 个低置信度 OCR 块，建议人工复核")

    return record
