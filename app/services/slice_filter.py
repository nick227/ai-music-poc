from __future__ import annotations

from app.domain.enums import AssignmentRole
from app.domain.models import MediaAsset, ReviewStatus, RightsStatus
from app.domain.slices import DatasetSliceFilter
from app.domain.taxonomy import MediaCategoryAssignment, MediaConceptAssignment


def _best_score(values: list[int | None]) -> int | None:
    scored = [value for value in values if value is not None]
    return max(scored) if scored else None


def matches_slice_filter(
    asset: MediaAsset,
    category_assignments: list[MediaCategoryAssignment],
    concept_assignments: list[MediaConceptAssignment],
    filter: DatasetSliceFilter,
) -> bool:
    if not asset.file_path:
        return False

    if filter.review_status is not None and asset.review_status != filter.review_status:
        return False

    if filter.rights_status is not None and asset.rights_status != filter.rights_status:
        return False

    if filter.concept_id is not None:
        if not any(item.concept_id == filter.concept_id for item in concept_assignments):
            return False

    if filter.category_ids:
        assigned = {item.category_id for item in category_assignments}
        if not all(category_id in assigned for category_id in filter.category_ids):
            return False

    if filter.roles:
        assigned_roles = {item.role for item in category_assignments}
        assigned_roles.update(item.role for item in concept_assignments)
        if not assigned_roles.intersection(set(filter.roles)):
            return False

    quality = _best_score([item.quality_score for item in category_assignments] + [item.quality_score for item in concept_assignments])
    if filter.min_quality is not None:
        if quality is None or quality < filter.min_quality:
            return False

    fit = _best_score([item.fit_score for item in category_assignments] + [item.fit_score for item in concept_assignments])
    if filter.min_fit is not None:
        if fit is None or fit < filter.min_fit:
            return False

    return True


def default_training_roles() -> list[AssignmentRole]:
    return [
        AssignmentRole.GOLD_REFERENCE,
        AssignmentRole.TRAINING_CANDIDATE,
        AssignmentRole.REFERENCE,
    ]
