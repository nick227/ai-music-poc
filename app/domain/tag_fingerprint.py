from __future__ import annotations

import hashlib

from app.domain.taxonomy import MediaCategoryAssignment, MediaConceptAssignment


def compute_tag_fingerprint(
    categories: list[MediaCategoryAssignment],
    concepts: list[MediaConceptAssignment],
) -> str:
    parts: list[str] = []
    for item in sorted(categories, key=lambda row: (row.category_id, row.role.value)):
        parts.append(f"c:{item.category_id}:{item.role.value}")
    for item in sorted(concepts, key=lambda row: (row.concept_id, row.role.value)):
        parts.append(f"x:{item.concept_id}:{item.role.value}")
    if not parts:
        return ""
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:32]


def already_ingested_with_fingerprint(
    ingested_fingerprint: str | None,
    ingestion_status,
    categories: list[MediaCategoryAssignment],
    concepts: list[MediaConceptAssignment],
) -> bool:
    from app.domain.enums import IngestionStatus

    current = compute_tag_fingerprint(categories, concepts)
    if ingested_fingerprint:
        return current == ingested_fingerprint
    return ingestion_status == IngestionStatus.INGESTED
