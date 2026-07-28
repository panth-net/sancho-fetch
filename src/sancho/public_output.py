"""Format ladder + writers for the public working output.

Separated from :mod:`sancho.project_export` (which orchestrates) so each file
stays focused. See ``project_export`` for the contract.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from sancho.path_utils import dedupe_name, normalize_extension, safe_slug, sanitize_zip_member
from sancho.templates.runtime.file_formats import ext_from_filename

DEFAULT_LARGE_FILE_BYTES = 100 * 1024 * 1024  # 100 MB

# Extension categories that drive the ladder for file-backed records.
_OPENABLE_KEEP = {"csv", "tsv", "xls", "xlsx", "xlsm", "ods", "pdf", "txt"}
_TABULAR_BINARY = {"parquet", "feather", "orc", "arrow"}
_GEOSPATIAL_NATIVE = {"geojson", "kml", "kmz", "gpkg", "gml", "shp", "shx", "dbf"}
_JSON_LIKE = {"json", "jsonl", "ndjson"}
_ARCHIVE = {"zip"}
_RECORD_LIST_KEYS = ("rows", "data", "results", "records", "items", "features")


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def timestamp(now: datetime | None = None) -> str:
    moment = now.astimezone(timezone.utc) if isinstance(now, datetime) else datetime.now(timezone.utc)
    return moment.strftime("%Y-%m-%d_%H%M%S")


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _stringify_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    # Nested object/array: keep losslessly as compact JSON text in the cell.
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


_GEOJSON_TYPES = {
    "FeatureCollection", "Feature", "GeometryCollection",
    "Point", "MultiPoint", "LineString", "MultiLineString",
    "Polygon", "MultiPolygon",
}


def _is_geojson(payload: Any) -> bool:
    """True for GeoJSON-shaped payloads (a `type` from the GeoJSON spec)."""
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("type"), str)
        and payload["type"] in _GEOJSON_TYPES
        and ("features" in payload or "geometry" in payload or "coordinates" in payload or "geometries" in payload)
    )


def _flatten_row(row: dict[str, Any]) -> dict[str, Any]:
    """Lift one level of all-scalar sub-dicts into dotted columns.

    ``{"country": {"id": "US", "value": "United States"}}`` becomes
    ``{"country.id": "US", "country.value": "United States"}`` -- lossless, and
    it keeps API rows like the World Bank's spreadsheet-friendly. Anything
    deeper (or colliding with an existing dotted key) is left as-is for
    ``_stringify_cell`` to keep as compact JSON.
    """
    flat: dict[str, Any] = {}
    for key, value in row.items():
        if (
            isinstance(value, dict)
            and value
            and all(_is_scalar(v) for v in value.values())
            and not any(f"{key}.{sub}" in row for sub in value)
        ):
            for sub, sub_value in value.items():
                flat[f"{key}.{sub}"] = sub_value
        else:
            flat[key] = value
    return flat


def extract_records(payload: Any) -> tuple[bool, list[dict[str, Any]], bool]:
    """Return ``(is_tabular, rows, has_nested)``.

    ``has_nested`` is True when any cell holds a non-scalar value, so the caller
    knows to also emit JSON alongside the CSV.
    """
    rows: list[dict[str, Any]] = []
    if isinstance(payload, list) and payload and all(isinstance(r, dict) for r in payload):
        rows = payload
    elif (
        isinstance(payload, list)
        and len(payload) == 2
        and isinstance(payload[0], dict)
        and isinstance(payload[1], list)
        and payload[1]
        and all(isinstance(r, dict) for r in payload[1])
    ):
        # Envelope shape, e.g. the World Bank API: [metadata, [rows]].
        rows = payload[1]
    elif isinstance(payload, dict):
        for key in _RECORD_LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list) and value and all(isinstance(r, dict) for r in value):
                rows = value
                break
        if not rows:
            # Provider-named envelope, e.g. OpenFEMA's
            # {"metadata": {...}, "DisasterDeclarationsSummaries": [...]}:
            # exactly one list-of-dicts value means it is the record list.
            candidates = [
                value
                for value in payload.values()
                if isinstance(value, list) and value and all(isinstance(r, dict) for r in value)
            ]
            if len(candidates) == 1:
                rows = candidates[0]
    if not rows:
        return False, [], False
    rows = [_flatten_row(row) for row in rows]
    has_nested = any(not _is_scalar(v) for row in rows for v in row.values())
    return True, rows, has_nested


# --- writers ------------------------------------------------------------------

def _fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    seen_set: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen_set:
                seen.append(key)
                seen_set.add(key)
    return seen


def render_csv(rows: list[dict[str, Any]]) -> str:
    seen = _fieldnames(rows)
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=seen, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _stringify_cell(row.get(k)) for k in seen})
    return buf.getvalue()


def write_csv(rows: list[dict[str, Any]], destination: Path) -> Path:
    # UTF-8-SIG (BOM) so accented / non-Latin text opens correctly in Excel and
    # Sheets. The csv module quotes commas, double quotes, and embedded newlines.
    destination.write_text(render_csv(rows), encoding="utf-8-sig", newline="")
    return destination


# Excel's format limit is 1,048,576 rows x 16,384 columns, and the app is
# unusable long before that. Above these bounds the table falls back to CSV:
# complete and machine-readable, where a giant .xlsx would truncate or hang.
XLSX_MAX_DATA_ROWS = 200_000
XLSX_MAX_COLUMNS = 16_000


def write_xlsx(rows: list[dict[str, Any]], destination: Path) -> Path:
    """Write rows as an Excel workbook, preserving payload types per cell.

    This is the default working format for tables because Excel corrupts CSV
    on open: leading zeros in code columns ("01003") are stripped, and
    non-US locales expect a different separator. In .xlsx, string values are
    text cells (codes survive verbatim) and numbers stay numbers -- there is
    nothing for Excel to guess.

    Streams via write-only mode (bounded memory) and strips the control
    characters that are illegal in XML but appear in real API data -- a CSV
    tolerates them, an .xlsx writer must not crash on them.
    """
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("data")
    sheet.freeze_panes = "A2"
    fields = _fieldnames(rows)
    bold = Font(bold=True)
    header = []
    for name in fields:
        cell = WriteOnlyCell(sheet, value=str(name))
        cell.font = bold
        header.append(cell)
    sheet.append(header)
    for row in rows:
        sheet.append([_xlsx_cell(row.get(key), ILLEGAL_CHARACTERS_RE) for key in fields])
    workbook.save(destination)
    return destination


def _xlsx_cell(value: Any, illegal_re: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = value if isinstance(value, str) else _stringify_cell(value)
    return illegal_re.sub("", text)


def write_json(payload: Any, destination: Path) -> Path:
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return destination


def copy_original(record_dir: Path, original_file: str, destination: Path) -> Path:
    """Copy the original artifact atomically (temp file + rename).

    A direct copy that is interrupted (process killed, disk full) would leave a
    truncated file that *looks* complete. Copy to a temp file in the same
    directory, then atomically rename, so the destination only ever appears once
    it is whole.
    """
    import os
    import shutil
    import tempfile

    src = record_dir / original_file
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(destination.parent), prefix=".sancho-tmp-")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        shutil.copystat(src, tmp)
        os.replace(tmp, destination)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return destination


def _is_shapefile_zip(zip_path: Path) -> bool:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = [n.lower() for n in zf.namelist()]
    except Exception:
        return False
    return any(n.endswith(".shp") for n in names)


def unzip_original(record_dir: Path, original_file: str, destination_dir: Path) -> list[Path]:
    """Extract a zip's members into ``destination_dir`` (guards against zip-slip)."""
    src = record_dir / original_file
    destination_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    dest_root = destination_dir.resolve()
    with zipfile.ZipFile(src) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            # Skip mac zip junk (__MACOSX/, ._*) and repair names that are
            # illegal on Windows (colons, reserved stems, trailing dots).
            member_rel = sanitize_zip_member(member.filename)
            if member_rel is None:
                continue
            target = (destination_dir / member_rel).resolve()
            if dest_root not in target.parents and target != dest_root:
                continue  # zip-slip guard
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as source, open(target, "wb") as handle:
                handle.write(source.read())
            written.append(target)
    return written


# --- the ladder ---------------------------------------------------------------

@dataclass
class OutputPlan:
    """One unit of public output for a single record."""

    kind: str  # "xlsx" | "csv" | "json" | "original" | "unzip"
    label: str
    ext: str = ""
    rows: list[dict[str, Any]] | None = None
    payload: Any = None
    original_file: str = ""


def _table_plan(label: str, rows: list[dict[str, Any]], table_fmt: str) -> OutputPlan:
    """Table working-copy plan; oversized tables fall back to CSV (Excel's
    format caps out at ~1M rows and the app is unusable well before that)."""
    fmt = table_fmt
    if fmt == "xlsx" and (
        len(rows) > XLSX_MAX_DATA_ROWS or len(_fieldnames(rows)) > XLSX_MAX_COLUMNS
    ):
        fmt = "csv"
    return OutputPlan(kind=fmt, label=label, ext=fmt, rows=rows)


def choose_public_outputs(
    record_dir: Path,
    payload: Any,
    provenance: dict[str, Any],
    label: str,
    *,
    prefer_csv: bool = True,
    keep_original_alongside: bool = True,
    unzip_archives: bool = True,
    tabular_format: str = "xlsx",
) -> list[OutputPlan]:
    """Walk the format ladder and return the OutputPlan(s) for one record.

    ``tabular_format`` is the working-copy format for clean tables: ``xlsx``
    (default; Excel-safe, keeps "01003"-style codes intact) or ``csv``.
    """
    table_fmt = tabular_format if tabular_format in ("csv", "xlsx") else "xlsx"

    source_kind = str(provenance.get("source_kind") or "api")
    original_file = str(provenance.get("original_file") or "")
    ext = ext_from_filename(original_file)

    if source_kind == "file" and original_file:
        if ext in _GEOSPATIAL_NATIVE:
            return [OutputPlan(kind="original", label=label, ext=ext, original_file=original_file)]
        if ext in _ARCHIVE:
            if unzip_archives and not _is_shapefile_zip(record_dir / original_file):
                return [OutputPlan(kind="unzip", label=label, ext=ext, original_file=original_file)]
            return [OutputPlan(kind="original", label=label, ext=ext, original_file=original_file)]
        if ext in _TABULAR_BINARY or (ext in ("csv", "tsv") and table_fmt == "xlsx"):
            # Parquet-like binaries need an openable copy; CSV/TSV sources get
            # an Excel-safe copy too (opening raw CSV in Excel strips leading
            # zeros). The faithful original is kept alongside either way.
            plans: list[OutputPlan] = []
            tabular, rows, _ = extract_records(payload)
            if prefer_csv and tabular:
                plans.append(_table_plan(label, rows, table_fmt))
            if keep_original_alongside or not plans:
                plans.append(OutputPlan(kind="original", label=label, ext=ext, original_file=original_file))
            return plans
        if ext in _OPENABLE_KEEP:
            return [OutputPlan(kind="original", label=label, ext=ext, original_file=original_file)]
        if ext not in _JSON_LIKE:
            return [OutputPlan(kind="original", label=label, ext=ext, original_file=original_file)]

    # API payload (or downloaded json): decide by shape.
    # GeoJSON keeps its structure -- never flatten geometry into a table.
    if _is_geojson(payload) or ext == "geojson":
        return [OutputPlan(kind="json", label=label, ext="geojson", payload=payload)]

    tabular, rows, has_nested = extract_records(payload)
    if prefer_csv and tabular and not has_nested:
        return [_table_plan(label, rows, table_fmt)]
    if prefer_csv and tabular and has_nested:
        return [
            _table_plan(label, rows, table_fmt),
            OutputPlan(kind="json", label=label, ext="json", payload=payload),
        ]
    json_ext = "geojson" if ext == "geojson" else "json"
    return [OutputPlan(kind="json", label=label, ext=json_ext, payload=payload)]


def write_plan(
    plan: OutputPlan,
    record_dir: Path,
    target_dir: Path,
    base_name: str,
    taken: set[str],
    large_file_bytes: int,
    large_files: list[dict[str, Any]],
) -> list[Path]:
    """Write one OutputPlan into ``target_dir``. Returns written file paths."""
    # Seed the dedupe set with names already on disk so a second export in the
    # same second (same timestamp + label) never silently overwrites the first.
    if target_dir.exists():
        for existing in target_dir.iterdir():
            taken.add(existing.name)

    if plan.kind == "unzip":
        folder_name = dedupe_name(base_name, taken)
        sub = target_dir / folder_name
        written = unzip_original(record_dir, plan.original_file, sub)
        if written:
            return written
        # Empty/degenerate archive: drop the empty folder and keep the original
        # zip so the user still gets the file they fetched.
        try:
            if sub.is_dir() and not any(sub.iterdir()):
                sub.rmdir()
                taken.discard(folder_name)
        except OSError:
            pass
        ext = normalize_extension(plan.ext) or ".zip"
        dest = target_dir / dedupe_name(f"{base_name}{ext}", taken)
        copy_original(record_dir, plan.original_file, dest)
        return [dest]

    ext = normalize_extension(plan.ext)
    filename = dedupe_name(f"{base_name}{ext}", taken)
    dest = target_dir / filename

    if plan.kind == "csv":
        write_csv(plan.rows or [], dest)
    elif plan.kind == "xlsx":
        write_xlsx(plan.rows or [], dest)
    elif plan.kind == "json":
        write_json(plan.payload, dest)
    elif plan.kind == "original":
        copy_original(record_dir, plan.original_file, dest)
    else:  # pragma: no cover - defensive
        return []

    size = dest.stat().st_size if dest.exists() else 0
    if size > large_file_bytes:
        cached = str(record_dir / plan.original_file) if plan.original_file else str(record_dir)
        large_files.append({"path": str(dest), "bytes": size, "cached_path": cached})
    return [dest]


def label_for(provenance: dict[str, Any], record_dir: Path, override: str | None) -> str:
    if override and str(override).strip():
        return safe_slug(str(override))
    family = str(provenance.get("family") or "").strip()
    module_id = str(provenance.get("module_id") or "").strip()
    base = family or module_id or record_dir.name or "dataset"
    return safe_slug(base)


__all__ = [
    "DEFAULT_LARGE_FILE_BYTES",
    "OutputPlan",
    "choose_public_outputs",
    "write_plan",
    "label_for",
    "extract_records",
    "render_csv",
    "write_csv",
    "write_xlsx",
    "write_json",
    "read_yaml",
    "read_json",
    "timestamp",
]
