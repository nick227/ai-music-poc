from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_song_service
from app.domain.enums import ReviewDecision
from app.domain.models import ReviewStatus, SongCompareResponse, SongListResponse, SongResponse, SongReviewRequest
from app.services.song_service import SongService

router = APIRouter(prefix="/api", tags=["songs"])


@router.get("/songs", response_model=SongListResponse)
def list_songs(
    limit: int = Query(default=25, ge=1, le=100),
    review_status: ReviewStatus | None = Query(default=None),
    review_decision: ReviewDecision | None = Query(default=None),
    style_version_id: str | None = Query(default=None, max_length=80),
    song_service: SongService = Depends(get_song_service),
):
    songs = song_service.list_songs(
        limit=limit,
        review_status=review_status,
        review_decision=review_decision,
        style_version_id=style_version_id,
    )
    return SongListResponse(songs=songs)


@router.get("/songs/compare", response_model=SongCompareResponse)
def compare_songs(
    baseline_id: str = Query(..., min_length=1),
    styled_id: str = Query(..., min_length=1),
    song_service: SongService = Depends(get_song_service),
):
    return song_service.compare_songs(baseline_id, styled_id)


@router.get("/songs/{song_id}", response_model=SongResponse)
def get_song(
    song_id: str,
    song_service: SongService = Depends(get_song_service),
):
    return song_service.get_song(song_id)


@router.post("/songs/{song_id}/review", response_model=SongResponse)
def review_song(
    song_id: str,
    request: SongReviewRequest,
    song_service: SongService = Depends(get_song_service),
):
    return song_service.submit_review(
        song_id,
        decision=request.decision,
        overall_score=request.overall_score,
        notes=request.notes,
    )
