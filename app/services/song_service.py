from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.core.errors import NotFoundError
from app.core.job_paths import stable_output_path
from app.domain.enums import ReviewDecision
from app.domain.models import (
    JobRecord,
    MediaAsset,
    MediaKind,
    ReviewStatus,
    SongCompareResponse,
    SongCompareSharedSettings,
    SongGenerationSummary,
    SongResponse,
)
from app.domain.version_details import normalize_version_details
from app.services.job_service import JobService
from app.storage.local_media_store import LocalMediaStore


class SongService:
    def __init__(self, media_store: LocalMediaStore, job_service: JobService) -> None:
        self.media_store = media_store
        self.job_service = job_service

    def list_songs(
        self,
        limit: int = 25,
        review_status: Optional[ReviewStatus] = None,
        review_decision: Optional[ReviewDecision] = None,
    ) -> list[SongResponse]:
        assets = self.media_store.list_generated_songs(limit=limit)
        if review_status is not None:
            assets = [item for item in assets if item.review_status == review_status]
        if review_decision is not None:
            assets = [item for item in assets if item.review_decision == review_decision]
        return [self.to_response(asset) for asset in assets]

    def list_by_style_version(self, style_version_id: str, limit: int = 50) -> list[SongResponse]:
        assets = self.media_store.list_generated_songs(limit=500)
        matched: list[SongResponse] = []
        for asset in assets:
            version_details = normalize_version_details(asset.version_details or {})
            if version_details.get("style_version_id") == style_version_id:
                matched.append(self.to_response(asset))
        return matched[:limit]

    def compare_songs(self, baseline_id: str, styled_id: str) -> SongCompareResponse:
        baseline = self.get_song(baseline_id)
        styled = self.get_song(styled_id)
        baseline_vd = baseline.version_details or {}
        styled_vd = styled.version_details or {}
        baseline_settings = baseline_vd.get("settings") or {}
        styled_settings = styled_vd.get("settings") or {}
        generator_name = None
        if baseline.generation_id:
            job = self.job_service.get(baseline.generation_id)
            if job is not None:
                generator_name = job.request.generator
        shared = SongCompareSharedSettings(
            prompt=baseline_vd.get("prompt") or styled_vd.get("prompt") or (baseline.generation.prompt if baseline.generation else None),
            seed=baseline_vd.get("seed") if baseline_vd.get("seed") is not None else styled_vd.get("seed"),
            duration_seconds=baseline_vd.get("duration_seconds") or styled_vd.get("duration_seconds") or baseline.duration_seconds,
            mode=baseline_settings.get("mode") or styled_settings.get("mode"),
            quality=baseline_settings.get("quality") or styled_settings.get("quality"),
            generator=generator_name,
        )
        return SongCompareResponse(
            baseline=baseline,
            styled=styled,
            shared=shared,
            style_version_id=styled_vd.get("style_version_id"),
            training_run_id=styled_vd.get("training_run_id"),
        )

    def get_song(self, song_id: str) -> SongResponse:
        asset = self._require_generated_song(song_id)
        return self.to_response(asset)

    def submit_review(
        self,
        song_id: str,
        decision: ReviewDecision,
        overall_score: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> SongResponse:
        asset = self._require_generated_song(song_id)
        review_status = ReviewStatus.REJECTED if decision == ReviewDecision.REJECT else ReviewStatus.REVIEWED
        updated = asset.model_copy(
            update={
                "review_decision": decision,
                "review_score": overall_score,
                "review_notes": notes,
                "review_status": review_status,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self.media_store.save(updated)
        return self.to_response(updated)

    def to_response(self, asset: MediaAsset) -> SongResponse:
        job: JobRecord | None = None
        if asset.generation_id:
            job = self.job_service.get(asset.generation_id)
        version_details = normalize_version_details(asset.version_details or {})
        return SongResponse(
            id=asset.id,
            title=asset.title,
            media_asset_id=asset.id,
            kind=asset.kind,
            file_path=asset.file_path,
            audio_url=f"/api/media/{asset.id}/audio" if asset.file_path else None,
            duration_seconds=asset.duration_seconds,
            sample_rate=asset.sample_rate,
            channels=asset.channels,
            review_status=asset.review_status,
            review_decision=asset.review_decision,
            review_score=asset.review_score,
            review_notes=asset.review_notes,
            generation_id=asset.generation_id,
            version_details=version_details,
            generation=_generation_summary(job),
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )

    def _require_generated_song(self, song_id: str) -> MediaAsset:
        asset = self.media_store.get(song_id)
        if asset is None or asset.kind != MediaKind.GENERATED_SONG:
            raise NotFoundError("Song not found")
        return asset


def _generation_summary(job: JobRecord | None) -> SongGenerationSummary | None:
    if job is None:
        return None
    version_details = normalize_version_details(job.version_details or {})
    return SongGenerationSummary(
        id=job.id,
        status=job.status,
        output_path=stable_output_path(job),
        prompt=job.request.prompt,
        lyrics=job.request.lyrics,
        seed=job.request.seed,
        backend=version_details.get("backend"),
        model_version=version_details.get("model_version"),
        created_at=job.created_at,
        finished_at=job.finished_at,
    )
