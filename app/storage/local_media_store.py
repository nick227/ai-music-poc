from pathlib import Path
from typing import List, Optional

from app.domain.models import MediaAsset, MediaKind, ReviewStatus


class LocalMediaStore:
    def __init__(self, media_dir: Path) -> None:
        self.media_dir = media_dir
        self.media_dir.mkdir(parents=True, exist_ok=True)

    def save(self, asset: MediaAsset) -> None:
        path = self.media_dir / f"{asset.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(asset.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    def get(self, asset_id: str) -> Optional[MediaAsset]:
        path = self.media_dir / f"{asset_id}.json"
        if not path.exists():
            return None
        return MediaAsset.model_validate_json(path.read_text(encoding="utf-8"))

    def list_recent(self, limit: int = 25) -> List[MediaAsset]:
        return self.list_filtered(limit=limit)

    def list_filtered(
        self,
        review_status: Optional[ReviewStatus] = None,
        kind: Optional[MediaKind] = None,
        limit: int = 50,
    ) -> List[MediaAsset]:
        records: list[MediaAsset] = []
        for path in self.media_dir.glob("*.json"):
            try:
                records.append(MediaAsset.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        if review_status is not None:
            records = [item for item in records if item.review_status == review_status]
        if kind is not None:
            records = [item for item in records if item.kind == kind]
        records.sort(key=lambda asset: asset.created_at, reverse=True)
        return records[:limit]

    def list_generated_songs(self, limit: int = 25) -> List[MediaAsset]:
        records = self.list_recent(limit=10_000)
        return [asset for asset in records if asset.kind == MediaKind.GENERATED_SONG][:limit]
