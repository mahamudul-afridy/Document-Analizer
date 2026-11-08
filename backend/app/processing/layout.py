"""Rebuild reading-order text lines from positioned words (PDF text layer or OCR)."""
from app.processing.types import Line, PageText, Word


def build_lines(page: PageText) -> list[Line]:
    """Group words into lines by vertical overlap, then sort left-to-right.

    Falls back to splitting raw text when no word positions are available (e.g. spreadsheets).
    """
    if not page.words:
        lines = []
        for i, raw in enumerate(page.text.splitlines()):
            tokens = raw.split()
            if tokens:
                n = len(tokens)
                words = [Word(t, j / max(n, 1), i * 0.01, (j + 1) / max(n, 1), i * 0.01 + 0.008) for j, t in
                         enumerate(tokens)]
                lines.append(Line(page.page_no, words))
        return lines

    words = sorted(page.words, key=lambda w: ((w.y0 + w.y1) / 2, w.x0))
    lines: list[list[Word]] = []
    for w in words:
        cy = (w.y0 + w.y1) / 2
        h = max(w.y1 - w.y0, 1e-4)
        placed = False
        for line in reversed(lines[-3:]):  # only look at recent lines
            ly0 = min(x.y0 for x in line)
            ly1 = max(x.y1 for x in line)
            lh = max(ly1 - ly0, 1e-4)
            if ly0 - 0.25 * h <= cy <= ly1 + 0.25 * h and abs(h - lh) < 1.5 * max(h, lh):
                line.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])

    result = []
    for line in lines:
        line.sort(key=lambda x: x.x0)
        result.append(Line(page.page_no, _merge_far_gaps(line)))
    result.sort(key=lambda ln: (ln.bbox[1], ln.bbox[0]))
    return result


def _merge_far_gaps(words: list[Word]) -> list[Word]:
    """Insert a column marker token when there is a big horizontal gap (helps table parsing)."""
    if len(words) < 2:
        return words
    out = [words[0]]
    for prev, cur in zip(words, words[1:]):
        gap = cur.x0 - prev.x1
        avg_char = max((prev.x1 - prev.x0) / max(len(prev.t), 1), 1e-4)
        if gap > 4 * avg_char:
            out.append(Word("\t", prev.x1, prev.y0, cur.x0, prev.y1, 1.0))
        out.append(cur)
    return out


def page_text_from_lines(lines: list[Line]) -> str:
    return "\n".join(ln.text.replace(" \t ", "    ") for ln in lines)
