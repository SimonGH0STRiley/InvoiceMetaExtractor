"""Layout clustering: reading order, lines, and semantic regions."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models import OcrBlock


@dataclass
class TextLine:
    """Horizontally clustered OCR blocks on one visual line."""

    blocks: list[OcrBlock] = field(default_factory=list)
    y_center: float = 0.0
    y_min: float = 0.0
    y_max: float = 0.0

    @property
    def text(self) -> str:
        sorted_blocks = sorted(self.blocks, key=lambda b: b.mid_x)
        return "".join(b.text for b in sorted_blocks)

    @property
    def merged_text_spaced(self) -> str:
        sorted_blocks = sorted(self.blocks, key=lambda b: b.mid_x)
        return " ".join(b.text for b in sorted_blocks)


@dataclass
class LayoutDocument:
    """Structured view of OCR blocks for one file (all pages)."""

    blocks: list[OcrBlock]
    lines: list[TextLine] = field(default_factory=list)
    page_heights: dict[int, float] = field(default_factory=dict)
    full_text: str = ""

    def blocks_on_page(self, page_index: int) -> list[OcrBlock]:
        return [b for b in self.blocks if b.page_index == page_index]


def _median_line_height(blocks: list[OcrBlock]) -> float:
    if not blocks:
        return 20.0
    heights = []
    for b in blocks:
        _, ymin, _, ymax = b.bbox
        h = ymax - ymin
        if h > 0:
            heights.append(h)
    if not heights:
        return 20.0
    heights.sort()
    mid = len(heights) // 2
    return heights[mid]


def cluster_lines(blocks: list[OcrBlock], *, y_tolerance_ratio: float = 0.6) -> list[TextLine]:
    """
    Group blocks into horizontal lines by Y overlap.
    y_tolerance_ratio * median_line_height defines merge threshold.
    """
    if not blocks:
        return []

    tol = _median_line_height(blocks) * y_tolerance_ratio
    sorted_blocks = sorted(blocks, key=lambda b: (b.page_index, b.mid_y, b.mid_x))

    lines: list[TextLine] = []
    current: list[OcrBlock] = []
    current_y: float | None = None

    for block in sorted_blocks:
        y = block.mid_y
        if current and current_y is not None and abs(y - current_y) <= tol and block.page_index == current[-1].page_index:
            current.append(block)
            current_y = sum(b.mid_y for b in current) / len(current)
        else:
            if current:
                lines.append(_blocks_to_line(current))
            current = [block]
            current_y = y

    if current:
        lines.append(_blocks_to_line(current))

    # reading order: page, then top-to-bottom
    lines.sort(key=lambda ln: (ln.blocks[0].page_index, ln.y_center, ln.blocks[0].mid_x))
    return lines


def _blocks_to_line(blocks: list[OcrBlock]) -> TextLine:
    ys = [b.mid_y for b in blocks]
    y_mins = [b.bbox[1] for b in blocks]
    y_maxs = [b.bbox[3] for b in blocks]
    return TextLine(
        blocks=blocks,
        y_center=sum(ys) / len(ys),
        y_min=min(y_mins),
        y_max=max(y_maxs),
    )


def estimate_page_height(blocks: list[OcrBlock], page_index: int) -> float:
    page_blocks = [b for b in blocks if b.page_index == page_index]
    if not page_blocks:
        return 1000.0
    return max(b.bbox[3] for b in page_blocks) * 1.05


def build_layout(blocks: list[OcrBlock]) -> LayoutDocument:
    """Build layout structure from raw OCR blocks."""
    lines = cluster_lines(blocks)
    page_indices = {b.page_index for b in blocks}
    page_heights = {pi: estimate_page_height(blocks, pi) for pi in page_indices}
    full_text = "\n".join(ln.text for ln in lines)
    return LayoutDocument(
        blocks=blocks,
        lines=lines,
        page_heights=page_heights,
        full_text=full_text,
    )


def top_region_blocks(layout: LayoutDocument, ratio: float = 0.25) -> list[OcrBlock]:
    """Blocks in the top fraction of the first page (for invoice title)."""
    first_page = 0
    h = layout.page_heights.get(first_page, 1000.0)
    cutoff = h * ratio
    return [
        b
        for b in layout.blocks
        if b.page_index == first_page and b.bbox[1] < cutoff
    ]


def blocks_between_anchors(
    layout: LayoutDocument,
    top_keyword: str,
    bottom_keyword: str,
    *,
    page_index: int = 0,
) -> list[OcrBlock]:
    """Blocks vertically between two label regions (e.g. 销售方 / 购买方)."""
    page_blocks = [b for b in layout.blocks if b.page_index == page_index]
    top_y: float | None = None
    bottom_y: float | None = None

    for b in page_blocks:
        t = b.text.replace(" ", "")
        if top_keyword in t and top_y is None:
            top_y = b.bbox[3]
        if bottom_keyword in t:
            bottom_y = b.bbox[1]

    if top_y is None:
        return page_blocks
    if bottom_y is None:
        return [b for b in page_blocks if b.bbox[1] > top_y]

    return [b for b in page_blocks if top_y < b.bbox[1] < bottom_y]
