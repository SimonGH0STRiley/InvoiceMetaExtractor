"""Cross-field validation (amount + tax vs totals)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from core.models import InvoiceRecord

TOLERANCE = 0.02

_RE_TOTAL_WITH_TAX = re.compile(
    r"价税合计(?:\(?(?:小写|大写)?\)?)?[：:\s]*[¥￥]?\s*([\d,]+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_RE_MONEY_FALLBACK = re.compile(r"[\d,]+\.\d{2}")


def _parse_total_with_tax(raw_text: str) -> float | None:
    """Extract 价税合计 from full OCR text."""
    if not raw_text:
        return None
    m = _RE_TOTAL_WITH_TAX.search(raw_text)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    # fallback: line containing 价税合计
    for line in raw_text.splitlines():
        if "价税合计" in line:
            nums = _RE_MONEY_FALLBACK.findall(line.replace("，", ","))
            if nums:
                try:
                    return float(nums[-1].replace(",", ""))
                except ValueError:
                    continue
    return None


def _downgrade_status(record: InvoiceRecord) -> None:
    if record.status == "success":
        record.status = "partial"


def _exceeds_tolerance(left: float, right: float, tolerance: float = TOLERANCE) -> bool:
    try:
        diff = abs(Decimal(str(left)) - Decimal(str(right)))
        return diff > Decimal(str(tolerance))
    except InvalidOperation:
        return abs(left - right) > tolerance


def _validate_line_item_totals(record: InvoiceRecord) -> None:
    if not record.line_items:
        return

    item_amounts = [item.amount for item in record.line_items if item.amount is not None]
    if record.amount is not None and len(item_amounts) == len(record.line_items):
        line_amount_total = sum(item_amounts)
        if _exceeds_tolerance(line_amount_total, record.amount):
            record.warnings.append(
                f"明细金额合计({line_amount_total:.2f})与票面合计金额({record.amount:.2f})不一致，请人工复核"
            )
            _downgrade_status(record)

    item_tax_amounts = [
        item.tax_amount for item in record.line_items if item.tax_amount is not None
    ]
    if record.tax_amount is not None and len(item_tax_amounts) == len(record.line_items):
        line_tax_total = sum(item_tax_amounts)
        if _exceeds_tolerance(line_tax_total, record.tax_amount):
            record.warnings.append(
                f"明细税额合计({line_tax_total:.2f})与票面合计税额({record.tax_amount:.2f})不一致，请人工复核"
            )
            _downgrade_status(record)


def _validate_total_with_tax(record: InvoiceRecord) -> bool:
    if record.amount is None or record.tax_amount is None:
        return False

    computed = record.amount + record.tax_amount
    total_declared = _parse_total_with_tax(record.raw_ocr_text)
    if total_declared is None:
        return False

    if _exceeds_tolerance(computed, total_declared):
        record.warnings.append(
            f"金额+税额({computed:.2f})与价税合计({total_declared:.2f})不一致，请人工复核"
        )
        _downgrade_status(record)
    return True


def _validate_tax_rate_fallback(record: InvoiceRecord) -> None:
    if record.amount is None or record.tax_amount is None:
        return
    if not record.tax_rate or record.tax_rate in ("免税", "不征税"):
        return

    rate_match = re.match(r"^(\d+(?:\.\d+)?)%$", record.tax_rate.strip())
    if not rate_match:
        return

    try:
        rate = float(rate_match.group(1)) / 100.0
        expected_tax = round(record.amount * rate, 2)
        if _exceeds_tolerance(expected_tax, record.tax_amount, TOLERANCE + 0.01):
            record.warnings.append(
                f"税额与税率推算({expected_tax:.2f})不一致，请人工复核"
            )
            _downgrade_status(record)
    except (ValueError, TypeError):
        pass


def validate_record(record: InvoiceRecord) -> InvoiceRecord:
    """Apply consistency checks and append warnings."""
    if record.amount is not None and record.amount < 0:
        record.warnings.append("金额(不含税)为负，请人工复核")
        _downgrade_status(record)

    if record.tax_amount is not None and record.tax_amount < 0:
        record.warnings.append("税额为负，请人工复核")
        _downgrade_status(record)

    _validate_line_item_totals(record)
    if not _validate_total_with_tax(record):
        _validate_tax_rate_fallback(record)

    return record
