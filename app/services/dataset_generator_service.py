from __future__ import annotations

from collections import defaultdict
import itertools

from app.domain.enums import DatasetSliceStatus, ConfidenceTier
from app.domain.slices import DatasetSlice, DatasetSliceFilter
from app.services.category_service import CategoryService
from app.services.ready_audio_service import ReadyAudioService
from app.services.slice_service import SliceService
from app.storage.assignment_store import AssignmentStore
from app.storage.local_media_store import LocalMediaStore


class DatasetGeneratorService:
    def __init__(
        self,
        slice_service: SliceService,
        category_service: CategoryService,
        assignment_store: AssignmentStore,
        media_store: LocalMediaStore,
        ready_audio_service: ReadyAudioService,
    ) -> None:
        self.slice_service = slice_service
        self.category_service = category_service
        self.assignment_store = assignment_store
        self.media_store = media_store
        self.ready_audio_service = ready_audio_service

    def generate_recommended_slices(self) -> list[DatasetSlice]:
        categories = self.category_service.list(include_archived=False)
        cat_lookup = {c.id: c for c in categories}
        
        media_to_cats = defaultdict(list)
        for assignment in self.assignment_store.list_category_assignments():
            media_to_cats[assignment.media_asset_id].append(assignment.category_id)

        candidates_map = defaultdict(list)

        for media_id, cat_ids in media_to_cats.items():
            asset = self.media_store.get(media_id)
            if not asset or not asset.duration_seconds:
                continue
            categories_for_media = self.assignment_store.list_category_assignments_for_media(media_id)
            concepts_for_media = self.assignment_store.list_concept_assignments_for_media(media_id)
            if not self.ready_audio_service.is_ready(asset, categories_for_media, concepts_for_media):
                continue
            
            valid_cats = sorted([c for c in cat_ids if c in cat_lookup])
            if not valid_cats:
                continue
                
            for size in range(1, min(len(valid_cats), 3) + 1):
                for combo in itertools.combinations(valid_cats, size):
                    candidates_map[combo].append(asset)
                
        MIN_TRACKS = 3
        MIN_DURATION = 60.0
        
        candidates = []
        
        for cids, assets in candidates_map.items():
            total_dur = sum(a.duration_seconds for a in assets)
            if len(assets) >= MIN_TRACKS and total_dur >= MIN_DURATION:
                if len(assets) >= 10 and total_dur >= 300.0:
                    tier = ConfidenceTier.STRONG
                elif len(assets) >= 5 and total_dur >= 120.0:
                    tier = ConfidenceTier.TRAINABLE
                else:
                    tier = ConfidenceTier.CANDIDATE
                candidates.append((list(cids), assets, tier))

        existing_slices = self.slice_service.list_slices()
        results = []

        for cids, assets, tier in candidates:
            media_ids = sorted([a.id for a in assets])
            filter_obj = DatasetSliceFilter(category_ids=cids)
            
            existing = None
            for s in existing_slices:
                if s.is_auto_generated and s.status == DatasetSliceStatus.DRAFT and s.filter.category_ids == cids:
                    existing = s
                    break

            if existing is not None:
                updates = {}
                if sorted(existing.media_ids) != media_ids:
                    updates["media_ids"] = media_ids
                if getattr(existing, "confidence_tier", None) != tier:
                    updates["confidence_tier"] = tier
                    
                if updates:
                    existing = self.slice_service.update(existing.id, **updates)
                results.append(existing)
            else:
                lineage_parent = None
                latest_version = 0
                for s in existing_slices:
                    if s.is_auto_generated and s.filter.category_ids == cids:
                        if s.version > latest_version:
                            latest_version = s.version
                            lineage_parent = s
                
                cat_names = [cat_lookup[cid].name for cid in cids]
                base_name = " + ".join(cat_names) + " Dataset"
                
                new_slice = self.slice_service.create(
                    name=base_name,
                    filter=filter_obj,
                    description=f"Auto-generated recommended dataset for {', '.join(cat_names)}",
                    media_ids=media_ids,
                )
                
                updates = {"is_auto_generated": True, "confidence_tier": tier}
                if lineage_parent:
                    updates["lineage_parent_id"] = lineage_parent.id
                    updates["version"] = lineage_parent.version + 1
                    updates["name"] = f"{base_name} v{updates['version']}"
                    
                updated = new_slice.model_copy(update=updates)
                self.slice_service.slice_store.save(updated)
                results.append(updated)

        return results
