import json
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def should_auto_polish(
    generator_name: str,
    quality_mode: str,
    auto_polish_override: bool | None = None,
) -> bool:
    if auto_polish_override is not None:
        return auto_polish_override
    if generator_name not in ("ace-cpp", "ace-step-command"):
        return False
    if quality_mode == "draft":
        return False
    return True


def auto_polish(target_path: Path, generator_name: str, quality_mode: str, auto_polish_override: bool = None) -> dict[str, Any]:
    """
    Applies post-processing to a generated WAV file selectively.
    
    1. Always renames `target_path` to `{stem}_raw.wav` to preserve raw output.
    2. Determines if polishing should be skipped based on generator/mode.
    3. Uses Pedalboard (if installed) or FFmpeg to create a polished WAV at `target_path`.
    4. If polishing is skipped or fails, `target_path` is not created (UI falls back to raw).
    
    Returns a metadata dictionary about the post-processing step.
    """
    start_time = time.time()
    if not target_path.exists():
        logger.warning(f"auto_polish: target_path does not exist {target_path}")
        return {"postprocess_skipped": True, "postprocess_skip_reason": "file_not_found"}

    enabled = True
    skip_reason = None
    if auto_polish_override is not None:
        enabled = auto_polish_override
        skip_reason = "Overridden by request config." if not enabled else None
    else:
        if not should_auto_polish(generator_name, quality_mode):
            enabled = False
            if generator_name not in ("ace-cpp", "ace-step-command"):
                skip_reason = f"Generator '{generator_name}' skips polishing by default."
            elif quality_mode == "draft":
                skip_reason = "Draft quality mode skips polishing."

    raw_path = target_path.with_name(f"{target_path.stem}_raw{target_path.suffix}")
    json_path = target_path.with_name(f"{target_path.stem}_postprocess.json")
    
    # 1. Preserve raw output
    shutil.move(str(target_path), str(raw_path))
    
    metadata: dict[str, Any] = {
        "postprocess_enabled": enabled,
        "postprocess_skipped": not enabled,
        "postprocess_skip_reason": skip_reason,
        "raw_audio_file": raw_path.name,
        "polished_audio_file": None,
        "chain_used": "none",
        "warnings": [],
        "elapsed_seconds": 0.0,
    }
    
    if not enabled:
        shutil.copy(str(raw_path), str(target_path))
        metadata["playback_file"] = target_path.name
        with open(json_path, "w") as f:
            json.dump(metadata, f, indent=2)
        return metadata
    
    success = False
    
    # 2. Try Pedalboard
    try:
        import pedalboard
        from pedalboard.io import AudioFile
        
        logger.info(f"auto_polish: applying Pedalboard chain to {raw_path}")
        with AudioFile(str(raw_path)) as f:
            audio = f.read(f.frames)
            samplerate = f.samplerate
            
        board = pedalboard.Pedalboard([
            pedalboard.HighpassFilter(cutoff_frequency_hz=40.0),
            pedalboard.Compressor(threshold_db=-15.0, ratio=4.0),
            pedalboard.Limiter(threshold_db=-1.0)
        ])
        
        effected = board(audio, samplerate)
        
        with AudioFile(str(target_path), 'w', samplerate, effected.shape[0]) as f:
            f.write(effected)
            
        metadata["chain_used"] = "pedalboard"
        metadata["polished_audio_file"] = target_path.name
        success = True
    except ImportError:
        metadata["warnings"].append("Pedalboard not installed. Falling back to FFmpeg.")
    except Exception as e:
        logger.exception("auto_polish: Pedalboard failed")
        metadata["warnings"].append(f"Pedalboard failed: {str(e)}")
        
    # 3. Fallback to FFmpeg if Pedalboard failed or wasn't available
    if not success:
        try:
            logger.info(f"auto_polish: applying FFmpeg chain to {raw_path}")
            # check if ffmpeg is available
            subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
            
            cmd = [
                "ffmpeg", "-y", "-i", str(raw_path),
                "-af", "highpass=f=40,afftdn=nr=10,loudnorm=I=-14:LRA=11:TP=-1.0",
                "-ar", "44100",
                str(target_path)
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            metadata["chain_used"] = "ffmpeg"
            metadata["polished_audio_file"] = target_path.name
            success = True
        except FileNotFoundError:
            metadata["warnings"].append("FFmpeg not found in PATH.")
        except subprocess.CalledProcessError as e:
            logger.error(f"auto_polish: FFmpeg failed with error: {e.stderr.decode('utf-8', errors='ignore') if e.stderr else 'Unknown'}")
            metadata["warnings"].append(f"FFmpeg failed: {e.returncode}")
        except Exception as e:
            logger.exception("auto_polish: FFmpeg failed")
            metadata["warnings"].append(f"FFmpeg fallback failed: {str(e)}")
            
    # 4. If both failed, just record it as skipped
    if not success:
        logger.warning(f"auto_polish: all chains failed for {target_path}")
        metadata["postprocess_skipped"] = True
        metadata["postprocess_skip_reason"] = "All polishing chains failed."
        
    metadata["elapsed_seconds"] = round(time.time() - start_time, 2)
    
    # Write metadata JSON beside it
    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=2)
        
    return metadata
