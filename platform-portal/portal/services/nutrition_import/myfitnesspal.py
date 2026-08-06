from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import PurePosixPath

MAX_UNCOMPRESSED_BYTES = 10 * 1024 * 1024
MAX_ZIP_MEMBERS = 10


@dataclass(frozen=True)
class ImportPreview:
    checksum: str
    rows: list[dict[str, object]]
    warnings: list[str]


class ImportFormatError(ValueError):
    pass


class MyFitnessPalFileProvider:
    name = "myfitnesspal_file"

    def preview(self, payload: bytes, filename: str) -> ImportPreview:
        checksum = hashlib.sha256(payload).hexdigest()
        lower = filename.lower()
        if lower.endswith(".zip"):
            files = self._zip_csvs(payload)
        elif lower.endswith(".csv"):
            files = [(filename, payload)]
        else:
            raise ImportFormatError("Upload a MyFitnessPal .zip or .csv export.")

        totals: dict[date, dict[str, float | None]] = {}
        warnings: list[str] = []
        nutrition_found = False
        for member_name, content in files:
            parsed, is_nutrition, file_warnings = self._parse_csv(content, member_name)
            nutrition_found |= is_nutrition
            warnings.extend(file_warnings)
            for day, values in parsed.items():
                current = totals.setdefault(day, {key: None for key in ("calories", "protein_g", "carbohydrate_g", "fat_g", "fibre_g", "bodyweight_kg")})
                for key, value in values.items():
                    if value is None:
                        continue
                    if key == "bodyweight_kg":
                        current[key] = value
                    else:
                        current[key] = (current[key] or 0) + value
        if not nutrition_found:
            raise ImportFormatError("No recognised MyFitnessPal nutrition columns were found.")
        rows = []
        for day, values in sorted(totals.items()):
            missing = [key for key in ("calories", "protein_g", "carbohydrate_g", "fat_g") if values[key] is None]
            rows.append({"date": day.isoformat(), **values, "missing": missing, "is_partial": bool(missing)})
        if not rows:
            raise ImportFormatError("The export contains no nutrition rows with valid dates.")
        return ImportPreview(checksum, rows, warnings)

    def _zip_csvs(self, payload: bytes) -> list[tuple[str, bytes]]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(payload))
        except zipfile.BadZipFile as exc:
            raise ImportFormatError("The ZIP file is malformed.") from exc
        members = archive.infolist()
        if len(members) > MAX_ZIP_MEMBERS or sum(m.file_size for m in members) > MAX_UNCOMPRESSED_BYTES:
            raise ImportFormatError("The ZIP expands beyond the safe import limit.")
        result = []
        for member in members:
            path = PurePosixPath(member.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts:
                raise ImportFormatError("The ZIP contains an unsafe path.")
            if member.is_dir() or not member.filename.lower().endswith(".csv"):
                continue
            result.append((path.name, archive.read(member)))
        if not result:
            raise ImportFormatError("The ZIP contains no CSV files.")
        return result

    def _parse_csv(self, content: bytes, filename: str):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ImportFormatError(f"{filename} is not UTF-8 CSV.") from exc
        try:
            reader = csv.DictReader(io.StringIO(text))
            headers = reader.fieldnames or []
        except csv.Error as exc:
            raise ImportFormatError(f"{filename} is malformed CSV.") from exc
        normalized = {self._norm(value): value for value in headers}
        date_col = self._find(normalized, "date")
        aliases = {
            "calories": ("calories",), "protein_g": ("protein g", "protein"),
            "carbohydrate_g": ("carbohydrates g", "carbohydrate g", "carbs g", "carbohydrates"),
            "fat_g": ("fat g", "fat"), "fibre_g": ("fiber g", "fibre g", "fiber", "fibre"),
            "bodyweight_kg": ("weight", "weight kg", "bodyweight kg"),
        }
        columns = {key: self._find(normalized, *names) for key, names in aliases.items()}
        nutrition = any(columns[key] for key in ("calories", "protein_g", "carbohydrate_g", "fat_g"))
        if not date_col or not any(columns.values()):
            return {}, False, []
        output: dict[date, dict[str, float | None]] = {}
        warnings = []
        try:
            for line, row in enumerate(reader, 2):
                day = self._date(row.get(date_col, ""))
                if day is None:
                    warnings.append(f"{filename} row {line}: invalid date skipped")
                    continue
                values = {key: self._number(row.get(column)) if column else None for key, column in columns.items()}
                if any(value is not None for value in values.values()):
                    output[day] = values if day not in output else self._combine(output[day], values)
        except csv.Error as exc:
            raise ImportFormatError(f"{filename} is malformed CSV.") from exc
        return output, nutrition, warnings

    @staticmethod
    def _norm(value: str) -> str:
        return " ".join(value.strip().lower().replace("(", " ").replace(")", " ").replace("_", " ").split())

    @staticmethod
    def _find(headers, *aliases):
        return next((headers[name] for name in aliases if name in headers), None)

    @staticmethod
    def _date(value: str) -> date | None:
        value = value.strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try: return datetime.strptime(value, fmt).date()
            except ValueError: pass
        return None

    @staticmethod
    def _number(value: str | None) -> float | None:
        if value is None or not value.strip(): return None
        try: return float(value.replace(",", "").strip())
        except ValueError: return None

    @staticmethod
    def _combine(left, right):
        return {key: (left[key] or 0) + (right[key] or 0) if left[key] is not None or right[key] is not None else None for key in left}
