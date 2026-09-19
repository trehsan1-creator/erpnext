"""Persistent library of learned, declarative parser profiles."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from core.parser_config import ParserProfile
from core.text import normalize_persian


class ParserProfileStore:
    def __init__(self, data_root: Path) -> None:
        self.directory = data_root / "parser_profiles"
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, profile: ParserProfile) -> Path:
        path = self.directory / f"{profile.profile_id}.json"
        path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        return path

    def all(self) -> list[ParserProfile]:
        profiles: list[ParserProfile] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                profiles.append(ParserProfile.model_validate_json(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                # A damaged profile is ignored rather than breaking all imports.
                continue
        return profiles

    def find_match(self, source: Path) -> ParserProfile | None:
        extension = source.suffix.lower().lstrip(".")
        for profile in sorted(self.all(), key=lambda item: item.usage_count, reverse=True):
            if profile.file_type != extension:
                continue
            try:
                headers = self._headers(source, profile)
            except Exception:
                continue
            expected = {normalize_persian(item) for item in self._mapped_headers(profile)}
            if expected and expected.issubset(set(headers)):
                profile.usage_count += 1
                profile.last_used_at = datetime.now(timezone.utc)
                profile.signature_headers = headers
                self.save(profile)
                return profile
        return None

    @staticmethod
    def _mapped_headers(profile: ParserProfile) -> list[str]:
        return [str(value) for value in profile.columns.model_dump().values() if value]

    @staticmethod
    def _headers(source: Path, profile: ParserProfile) -> list[str]:
        if profile.file_type == "csv":
            frame = pd.read_csv(source, header=profile.header_row - 1, nrows=0, encoding=profile.encoding)
        else:
            frame = pd.read_excel(source, sheet_name=profile.sheet_name, header=profile.header_row - 1, nrows=0)
        return [normalize_persian(item) for item in frame.columns]

    def summary(self) -> list[dict[str, Any]]:
        return [
            {
                "profile_id": item.profile_id,
                "name": item.profile_name,
                "file_type": item.file_type,
                "usage_count": item.usage_count,
                "confidence": item.confidence,
                "last_used_at": item.last_used_at.isoformat() if item.last_used_at else None,
            }
            for item in self.all()
        ]
