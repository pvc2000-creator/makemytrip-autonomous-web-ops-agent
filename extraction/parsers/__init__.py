"""Schema-driven HTML parser (Beautiful Soup).

Confidence model:
  start at 1.0
  -0.25 when the item container was found only through a fallback selector (layout drift)
  -0.10 per field resolved through a fallback selector
  -0.30 per missing required field
  -0.10 per normalizer warning (ambiguous currency, unparsed date ...)
"""
import hashlib

from bs4 import BeautifulSoup

from extraction.normalizers import NORMALIZERS, clean_text, normalize_location
from extraction.schemas import ExtractionSchema, Record


def _find(node, spec, page):
    """Return (raw_value, used_fallback). Looks inside the item first, then the whole page."""
    for scope in (node, page):
        for i, sel in enumerate(spec.selectors):
            el = scope.select_one(sel) if sel else None
            if el is None and scope is node and hasattr(node, "attrs") and spec.attr and node.has_attr(spec.attr):
                v = node[spec.attr]
                return (" ".join(v) if isinstance(v, list) else v), False
            if el is not None:
                raw = el.get(spec.attr) if spec.attr else el.get_text(" ", strip=True)
                if isinstance(raw, list):
                    raw = " ".join(raw)
                if raw:
                    return raw, i > 0
    return None, False


def entity_key(schema: ExtractionSchema, fields: dict) -> str:
    parts = [str(fields.get(f) or "").lower() for f in schema.entity_fields]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def parse(html: str, url: str, schema: ExtractionSchema) -> tuple[list[Record], list[str]]:
    """Returns records plus page-level warnings."""
    soup = BeautifulSoup(html, "html.parser")
    warnings: list[str] = []
    items, used_item_fallback = [], False
    for i, sel in enumerate(schema.item_selectors):
        items = soup.select(sel)
        if items:
            used_item_fallback = i > 0 and not schema.page_level
            if used_item_fallback:
                warnings.append(f"layout_changed: primary container '{schema.item_selectors[0]}' missing, used '{sel}'")
            break
    if schema.page_level:
        items = items[:1]
    if not items:
        warnings.append("no_items: none of the container selectors matched; page structure may have changed")
        return [], warnings

    records, seen = [], set()
    for node in items:
        conf, notes, fields = 1.0, [], {}
        if used_item_fallback:
            conf -= 0.25
            notes.append("container found via fallback selector")
        for name, spec in schema.fields.items():
            raw, fallback = _find(node, spec, soup)
            if raw is None:
                fields[name] = None
                if spec.required:
                    conf -= 0.30
                    notes.append(f"missing required field '{name}'")
                continue
            if fallback:
                conf -= 0.10
                notes.append(f"'{name}' found via fallback selector")
            if spec.kind in NORMALIZERS:
                value, note = NORMALIZERS[spec.kind](raw)
                if note:
                    conf -= 0.10
                    notes.append(f"{name}: {note}")
            else:
                value = clean_text(raw)
                if name in ("destination", "city"):
                    value = normalize_location(value)
            fields[name] = value
        key = entity_key(schema, fields)
        if key in seen:
            warnings.append(f"duplicate record skipped for entity {key}")
            continue
        seen.add(key)
        entity = " / ".join(str(fields.get(f) or "?") for f in schema.entity_fields)
        records.append(Record(
            entity_key=key, entity=entity, fields=fields,
            snippet=clean_text(node.get_text(" ", strip=True))[:280],
            source_url=url, confidence=round(max(0.0, min(1.0, conf)), 2), validation_notes=notes))
    return records, warnings
