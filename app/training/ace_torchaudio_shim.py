"""Import-time shim: route torchaudio.load through soundfile for ACE preprocess."""

from __future__ import annotations

import soundfile as sf
import torch
import torchaudio


def _load_soundfile(uri, frame_offset=0, num_frames=-1, normalize=True, channels_first=True, format=None, **kwargs):
    del frame_offset, num_frames, normalize, format, kwargs
    data, sample_rate = sf.read(str(uri), dtype="float32", always_2d=True)
    tensor = torch.from_numpy(data.T.copy())
    if not channels_first:
        tensor = tensor.T
    return tensor, sample_rate


torchaudio.load = _load_soundfile
