from app.domain.presets import get_preset, list_presets


class PresetService:
    def list(self):
        return list_presets()

    def get(self, preset_id: str):
        return get_preset(preset_id)
