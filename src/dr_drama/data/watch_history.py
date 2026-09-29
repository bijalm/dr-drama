"""Explicit, atomic metadata updates to the local collection CSV."""

import csv
import json
import os
from pathlib import Path
import tempfile

USER_FIELDS = ("title", "my_rating", "status", "favorite", "would_rewatch", "personal_notes")
EXTERNAL_FIELDS = ("canonical_title", "original_title", "release_year", "country", "original_language", "genres", "main_cast", "number_of_episodes", "public_rating", "public_vote_count", "popularity", "popularity_metric", "synopsis", "keywords", "external_api_id", "metadata_source", "source_url", "metadata_retrieved_at")
STATUSES = {"completed", "dropped", "unfinished", "watching"}


def save_metadata(path: Path, title: str, metadata: dict, status: str | None = None) -> None:
    """Append or refresh one record, preserving every existing user field.

    Reject duplicate matches and conflicting source IDs. Missing refreshed fields
    preserve existing metadata. This local writer assumes one active writer.
    """
    if not title.strip() or not metadata.get("external_api_id") or not metadata.get("metadata_source"):
        raise ValueError("Title and metadata source/ID are required.")
    rows = []
    fields = list(USER_FIELDS + EXTERNAL_FIELDS)
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or set(reader.fieldnames) != set(fields):
                raise ValueError("Watch-history CSV headers do not match the schema.")
            fields = reader.fieldnames
            rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError("Watch-history CSV contains malformed rows.")
    matches = [row for row in rows if (row['external_api_id'] == str(metadata['external_api_id']) and row['metadata_source'] == metadata['metadata_source']) or row['title'].strip().casefold() == title.strip().casefold()]
    if len(matches) > 1:
        raise ValueError("Multiple existing rows match. Resolve duplicates before saving.")
    if matches:
        row = matches[0]
        if row['external_api_id'] and (row['external_api_id'], row['metadata_source']) != (str(metadata['external_api_id']), metadata['metadata_source']):
            raise ValueError("Existing title is linked to a different external record. No changes saved.")
    else:
        if status not in STATUSES:
            raise ValueError("A valid viewing status is required for a new watch-history row.")
        row = dict.fromkeys(fields, "")
        row.update(title=title.strip(), status=status)
        rows.append(row)
    for field in EXTERNAL_FIELDS:
        value = metadata.get(field)
        if value is not None:
            row[field] = json.dumps(value, ensure_ascii=False) if isinstance(value, list) else str(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False) as stream:
            temporary = stream.name
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
