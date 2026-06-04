"""Field aliases, spatial strategies, and value validation patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Pattern


class SpatialStrategy(str, Enum):
    RIGHT_SAME_ROW = "right_same_row"
    BELOW = "below"
    RIGHT_OR_BELOW = "right_or_below"
    TOP_TITLE = "top_title"
    REGION_BETWEEN = "region_between"
    TABLE_TAIL = "table_tail"
    FULL_TEXT = "full_text"


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label_aliases: tuple[str, ...]
    strategy: SpatialStrategy
    value_pattern: Pattern[str] | None = None
    normalize: str | None = None  # date | money | percent | tax_id


# --- regex patterns ---
RE_INVOICE_NUMBER = re.compile(r"^\d{8,30}$")
RE_DATE = re.compile(
    r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
    r"|(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})"
)
RE_DATE_LOOSE = re.compile(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})")
RE_TAX_ID = re.compile(r"^[A-Z0-9]{15,20}$", re.I)
RE_MONEY = re.compile(r"^¥?\s*([\d,]+(?:\.\d{1,2})?)$")
RE_TAX_RATE = re.compile(r"^(\d+(?:\.\d+)?%|免税|不征税|0%|—|-)$")

FIELD_SPECS: list[FieldSpec] = [
    FieldSpec(
        key="invoice_type",
        label_aliases=("发票",),
        strategy=SpatialStrategy.TOP_TITLE,
    ),
    FieldSpec(
        key="invoice_number",
        label_aliases=("发票号码", "发票代码", "Number", "No."),
        strategy=SpatialStrategy.RIGHT_OR_BELOW,
        value_pattern=re.compile(r"\d{8,30}"),
    ),
    FieldSpec(
        key="issue_date",
        label_aliases=("开票日期", "日期"),
        strategy=SpatialStrategy.RIGHT_OR_BELOW,
        normalize="date",
    ),
    FieldSpec(
        key="seller_name",
        label_aliases=("销售方", "销方", "销售方名称", "名称"),
        strategy=SpatialStrategy.REGION_BETWEEN,
    ),
    FieldSpec(
        key="tax_items",
        label_aliases=("项目名称",),
        strategy=SpatialStrategy.FULL_TEXT,
    ),
    FieldSpec(
        key="amount",
        label_aliases=("合计", "金额", "不含税", "价税合计"),
        strategy=SpatialStrategy.TABLE_TAIL,
        value_pattern=RE_MONEY,
        normalize="money",
    ),
    FieldSpec(
        key="tax_amount",
        label_aliases=("税额", "合计税额", "税金"),
        strategy=SpatialStrategy.TABLE_TAIL,
        value_pattern=RE_MONEY,
        normalize="money",
    ),
    FieldSpec(
        key="tax_rate",
        label_aliases=("税率", "征收率"),
        strategy=SpatialStrategy.RIGHT_OR_BELOW,
        value_pattern=RE_TAX_RATE,
        normalize="percent",
    ),
]

# Label fuzzy match: strip spaces/punctuation
def normalize_label(text: str) -> str:
    return re.sub(r"[\s:：·.]", "", text)


def label_matches(block_text: str, aliases: tuple[str, ...], threshold: float = 0.6) -> bool:
    """Check if OCR block text matches any field label alias."""
    t = normalize_label(block_text)
    if not t:
        return False
    for alias in aliases:
        a = normalize_label(alias)
        if not a:
            continue
        if a in t or t in a:
            return True
        # partial overlap for short labels
        if len(a) >= 2 and a[:2] in t:
            return True
    return False
