from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

MAX_SHEETS = 24
MAX_ROWS = 5000
MAX_COLUMNS = 80
MAX_CELL_CHARS = 2000
FIELDS = ("athlete", "date", "week", "session", "exercise", "sets", "reps", "load", "rpe", "notes", "variation", "lift_family")
ALIASES = {
    "athlete": {"athlete", "athlete name", "client", "lifter"},
    "date": {"date", "training date", "session date", "performed date"},
    "week": {"week", "week number", "training week", "block week"},
    "session": {"session", "day", "training day", "session day", "workout"},
    "exercise": {"exercise", "movement", "lift", "exercise name"},
    "sets": {"sets", "set count", "number of sets"},
    "reps": {"reps", "repetitions", "rep count"},
    "load": {"load", "weight", "kg", "load kg", "weight kg"},
    "rpe": {"rpe", "rating of perceived exertion"},
    "notes": {"notes", "note", "comments", "comment"},
    "variation": {"variation", "exercise variation", "variant"},
    "lift_family": {"lift family", "family", "movement family"},
}


class ImportFormatError(ValueError): pass


@dataclass(frozen=True)
class Workbook:
    filename: str
    checksum: str
    sheets: list[dict]
    formula_cells: int = 0


def _xml(payload: bytes):
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ImportFormatError("XLSX files containing XML entities are not supported.")
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ImportFormatError("The XLSX workbook XML is malformed.") from exc


def _text(value: object) -> str:
    value = "" if value is None else str(value)
    return value.replace("\x00", "").strip()[:MAX_CELL_CHARS]


def _csv(payload: bytes, filename: str) -> Workbook:
    if b"\x00" in payload[:4096]:
        raise ImportFormatError("The CSV content is not plain text.")
    try:
        decoded = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFormatError("CSV files must use UTF-8 text encoding.") from exc
    try:
        rows = [[_text(v) for v in row] for row in csv.reader(io.StringIO(decoded))]
    except csv.Error as exc:
        raise ImportFormatError("The CSV structure is malformed.") from exc
    _bound(rows)
    return Workbook(filename, hashlib.sha256(payload).hexdigest(), [{"name": "CSV", "rows": rows}])


def _xlsx(payload: bytes, filename: str) -> Workbook:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ImportFormatError("The XLSX file is not a valid workbook.") from exc
    names = set(archive.namelist())
    if "xl/workbook.xml" not in names or "[Content_Types].xml" not in names:
        raise ImportFormatError("The XLSX package is missing required workbook data.")
    if any(name.casefold().endswith("vbaproject.bin") for name in names):
        raise ImportFormatError("Macro-enabled workbooks are not supported.")
    total_uncompressed = sum(item.file_size for item in archive.infolist())
    if total_uncompressed > 50 * 1024 * 1024:
        raise ImportFormatError("The expanded workbook is too large.")
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    rel_ns = {"p": "http://schemas.openxmlformats.org/package/2006/relationships"}
    shared: list[str] = []
    if "xl/sharedStrings.xml" in names:
        root = _xml(archive.read("xl/sharedStrings.xml"))
        shared = [_text("".join(node.itertext())) for node in root.findall("m:si", ns)]
    relationships = _xml(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {r.attrib["Id"]: r.attrib["Target"] for r in relationships.findall("p:Relationship", rel_ns)}
    workbook = _xml(archive.read("xl/workbook.xml"))
    sheet_defs = workbook.findall("m:sheets/m:sheet", ns)
    if len(sheet_defs) > MAX_SHEETS:
        raise ImportFormatError(f"Workbooks may contain at most {MAX_SHEETS} sheets.")
    result, formulas = [], 0
    for sheet in sheet_defs:
        target = targets.get(sheet.attrib.get(f"{{{ns['r']}}}id", ""), "")
        path = str(PurePosixPath("xl") / target) if not target.startswith("/") else target.lstrip("/")
        path = str(PurePosixPath(path))
        if path not in names:
            continue
        root = _xml(archive.read(path))
        rows: list[list[str]] = []
        for row_node in root.findall("m:sheetData/m:row", ns):
            values: dict[int, str] = {}
            for cell in row_node.findall("m:c", ns):
                ref = cell.attrib.get("r", "A1")
                letters = re.match(r"[A-Z]+", ref.upper())
                col = 0
                for ch in letters.group(0) if letters else "A": col = col * 26 + ord(ch) - 64
                if col > MAX_COLUMNS:
                    raise ImportFormatError(f"Sheets may contain at most {MAX_COLUMNS} columns.")
                if cell.find("m:f", ns) is not None:
                    formulas += 1
                    values[col - 1] = ""
                    continue
                value_node = cell.find("m:v", ns)
                inline = cell.find("m:is", ns)
                value = "" if value_node is None else value_node.text or ""
                if cell.attrib.get("t") == "s" and value.isdigit() and int(value) < len(shared): value = shared[int(value)]
                elif cell.attrib.get("t") == "inlineStr" and inline is not None: value = "".join(inline.itertext())
                values[col - 1] = _text(value)
            if values:
                width = max(values) + 1
                rows.append([values.get(i, "") for i in range(width)])
            else: rows.append([])
        _bound(rows)
        result.append({"name": _text(sheet.attrib.get("name", "Sheet")), "rows": rows})
    if not result:
        raise ImportFormatError("The workbook contains no readable worksheets.")
    return Workbook(filename, hashlib.sha256(payload).hexdigest(), result, formulas)


def _bound(rows: list[list[str]]) -> None:
    if len(rows) > MAX_ROWS: raise ImportFormatError(f"Sheets may contain at most {MAX_ROWS} rows.")
    if any(len(row) > MAX_COLUMNS for row in rows): raise ImportFormatError(f"Sheets may contain at most {MAX_COLUMNS} columns.")


def read_workbook(payload: bytes, filename: str) -> Workbook:
    suffix = PurePosixPath(filename).suffix.casefold()
    if suffix not in {".csv", ".xlsx"}: raise ImportFormatError("Only .csv and .xlsx files are supported.")
    if suffix == ".xlsx" and not payload.startswith(b"PK\x03\x04"): raise ImportFormatError("The file content does not match XLSX.")
    if suffix == ".csv" and payload.startswith(b"PK\x03\x04"): raise ImportFormatError("The file content does not match CSV.")
    return _xlsx(payload, filename) if suffix == ".xlsx" else _csv(payload, filename)


def normalize_heading(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.casefold())).strip()


def detect(sheet: dict) -> dict:
    best = (-1, 0, {})
    for index, row in enumerate(sheet["rows"][:30]):
        mapping, used = {}, set()
        for col, value in enumerate(row):
            heading = normalize_heading(value)
            matches = [field for field, aliases in ALIASES.items() if heading in aliases]
            if len(matches) == 1 and matches[0] not in used:
                mapping[matches[0]], used = col, used | {matches[0]}
        score = len(mapping) + (3 if "exercise" in mapping else 0)
        if score > best[0]: best = (score, index, mapping)
    _, header, mapping = best
    headings = sheet["rows"][header] if sheet["rows"] else []
    columns = []
    for index, heading in enumerate(headings):
        fields = [f for f, aliases in ALIASES.items() if normalize_heading(heading) in aliases]
        status = "mapped" if len(fields) == 1 else "ambiguous" if len(fields) > 1 else "unmapped"
        columns.append({"index": index, "heading": heading or f"Column {index + 1}", "field": fields[0] if len(fields) == 1 else "", "status": status, "confidence": "high" if status == "mapped" else "low"})
    return {"header_row": header, "mapping": mapping, "columns": columns}


def _number(value: str, field: str, integer: bool = False):
    if not value: return None
    cleaned = value.casefold().replace("kg", "").strip()
    try: number = float(cleaned)
    except ValueError: raise ImportFormatError(f"{field} must be numeric.")
    if number < 0 or (integer and not number.is_integer()): raise ImportFormatError(f"{field} is invalid.")
    return int(number) if integer else number


def interpret(sheet: dict, header_row: int, mapping: dict[str, int]) -> list[dict]:
    if "exercise" not in mapping: raise ImportFormatError("Map an Exercise column before continuing.")
    output, carried_date, carried_week, carried_session = [], "", "", ""
    for source_index, raw in enumerate(sheet["rows"][header_row + 1:], header_row + 2):
        if not any(raw): continue
        get = lambda field: _text(raw[mapping[field]]) if field in mapping and mapping[field] < len(raw) else ""
        carried_date, carried_week, carried_session = get("date") or carried_date, get("week") or carried_week, get("session") or carried_session
        exercise = get("exercise")
        if not exercise: continue
        item = {"source_row": source_index, "date": carried_date, "week": carried_week, "session": carried_session, "exercise": exercise,
                "athlete": get("athlete"), "sets": get("sets"), "reps": get("reps"), "load": get("load"), "rpe": get("rpe"), "notes": get("notes"), "variation": get("variation"), "lift_family": get("lift_family"), "errors": []}
        combined = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", item["sets"] or item["reps"])
        if combined: item["sets"], item["reps"] = combined.group(1), combined.group(2)
        try:
            item["sets_value"] = _number(item["sets"], "Sets", True) or 1
            item["reps_value"] = _number(item["reps"], "Reps", True)
            item["load_value"] = _number(item["load"], "Load")
            item["rpe_value"] = _number(item["rpe"], "RPE")
            if item["sets_value"] > 20: raise ImportFormatError("Sets exceeds the safe maximum of 20.")
            if item["rpe_value"] is not None and not 1 <= item["rpe_value"] <= 10: raise ImportFormatError("RPE must be between 1 and 10.")
            if item["date"]:
                parsed = None
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"):
                    try: parsed = datetime.strptime(item["date"], fmt).date(); break
                    except ValueError: pass
                if parsed is None: raise ImportFormatError("Date must be YYYY-MM-DD or an unambiguous day/month/year value.")
                item["date_value"] = parsed.isoformat()
            else: raise ImportFormatError("Training Date is required for safe historical import.")
        except (ImportFormatError, ValueError) as exc: item["errors"].append(str(exc))
        output.append(item)
    return output


def fingerprint(item: dict, set_number: int) -> str:
    values = [item.get(k) for k in ("date_value", "week", "session", "exercise", "reps_value", "load_value", "rpe_value", "notes", "variation", "lift_family")] + [set_number]
    normalized = [str(v).strip().casefold() if v is not None else "" for v in values]
    return hashlib.sha256(json.dumps(normalized, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
