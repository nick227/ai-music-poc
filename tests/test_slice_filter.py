from app.domain.enums import AssignmentRole
from app.domain.models import MediaAsset, MediaKind, MediaSource, ReviewStatus, RightsStatus
from app.domain.slices import DatasetSliceFilter
from app.domain.taxonomy import MediaCategoryAssignment, MediaConceptAssignment
from app.services.slice_filter import matches_slice_filter


def _asset(**overrides) -> MediaAsset:
    data = {
        "title": "Track",
        "kind": MediaKind.UPLOAD,
        "source": MediaSource.USER_IMPORT,
        "file_path": "uploads/track.wav",
        "review_status": ReviewStatus.REVIEWED,
        "rights_status": RightsStatus.CONFIRMED,
    }
    data.update(overrides)
    return MediaAsset(**data)


def test_matches_requires_file_path():
    asset = _asset(file_path=None)
    assert not matches_slice_filter(asset, [], [], DatasetSliceFilter())


def test_matches_roles_and_quality():
    asset = _asset()
    categories = [
        MediaCategoryAssignment(
            media_asset_id=asset.id,
            category_id="cat_genre_pop",
            role=AssignmentRole.GOLD_REFERENCE,
            quality_score=5,
            fit_score=4,
        )
    ]
    filt = DatasetSliceFilter(roles=[AssignmentRole.GOLD_REFERENCE], min_quality=4, min_fit=3)
    assert matches_slice_filter(asset, categories, [], filt)


def test_rejects_wrong_rights_status():
    asset = _asset(rights_status=RightsStatus.DO_NOT_TRAIN)
    filt = DatasetSliceFilter(rights_status=RightsStatus.CONFIRMED)
    assert not matches_slice_filter(asset, [], [], filt)
