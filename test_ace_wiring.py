import os
import asyncio
from pathlib import Path
from app.core.config import get_settings
from app.core.ace_runtime import load_runtime_profile, save_runtime_profile, AceRuntimeStatus
from app.domain.models import GenerationRequest
from app.services.generation_service import GenerationService
from app.services.job_service import JobService
from app.generators.registry import GeneratorRegistry
from app.generators.ace_step import AceStepCommandGenerator
from app.storage.local_file_store import LocalFileStore
from app.storage.local_media_store import LocalMediaStore
from app.storage.log_store import LogStore
from app.storage.metadata_store import MetadataStore
from app.services.style_version_service import StyleVersionService

def run_test():
    settings = get_settings()
    settings.ace_allow_fallback = False
    
    # 1. Setup mock services
    job_service = JobService(settings)
    file_store = LocalFileStore(settings.data_dir / "outputs")
    media_store = LocalMediaStore(settings)
    log_store = LogStore(settings)
    metadata_store = MetadataStore(settings)
    
    class MockStyleVersionService:
        pass
    
    registry = GeneratorRegistry()
    ace_generator = AceStepCommandGenerator(settings)
    
    # We will mock subprocess.run on AceStepGenerator to prevent actual execution,
    import subprocess
    original_run = subprocess.run
    captured_command = []
    
    def mock_run(cmd, *args, **kwargs):
        captured_command.extend(cmd)
        # Mock successful generation by creating the output file
        output_path = None
        for i, c in enumerate(cmd):
            if c == "--output":
                output_path = Path(cmd[i+1])
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            import wave
            with wave.open(str(output_path), 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(44100)
                wav.writeframes(b'\x00' * 44100 * 2)
                
        class MockCompletedProcess:
            returncode = 0
            stdout = "mock stdout"
            stderr = "mock stderr"
        return MockCompletedProcess()
        
    subprocess.run = mock_run
    
    # Mock template
    settings.ace_command_template = "mock_command --device $device --lm-model $lm_model --batch $batch_size --steps $inference_steps --output $output_path"
    
    registry.register(ace_generator)
    
    gen_service = GenerationService(
        registry=registry,
        job_service=job_service,
        file_store=file_store,
        media_store=media_store,
        log_store=log_store,
        metadata_store=metadata_store,
        style_version_service=MockStyleVersionService(),
        settings=settings
    )
    
    # 2. Test block when ace_usable is False
    profile_data = load_runtime_profile(settings.data_dir) or {}
    profile_data["ace_usable"] = False
    profile_data["user_message"] = "Mock unusable"
    save_runtime_profile(settings.data_dir, AceRuntimeStatus.model_validate(profile_data))
    
    req = GenerationRequest(prompt="test", generator="ace-step-command", duration_seconds=10)
    job = job_service.create_job(req)
    
    gen_service.run_job(job.id)
    
    job_record = job_service.get_required(job.id)
    assert job_record.status == "FAILED", "Job should fail when ACE is unusable"
    assert "ACE runtime is not usable" in job_record.error, "Error message should indicate ACE is unusable"
    print("Test 1 Passed: Generation blocked when ACE unusable.")
    
    # 3. Test success when ace_usable is True
    profile_data["ace_usable"] = True
    profile_data["checked_at"] = "2026-06-27T00:00:00Z"
    profile_data["hardware"] = {
        "safe_recommended_config": {
            "checkpoint": "turbo-1",
            "lm_model": "mock-lm-0.6B",
            "batch_size": 2,
            "duration": 10,
            "inference_steps": 12,
            "offload_to_cpu": True,
            "device": "cuda",
            "description": "Mock safe tier"
        }
    }
    save_runtime_profile(settings.data_dir, AceRuntimeStatus.model_validate(profile_data))
    
    req2 = GenerationRequest(prompt="test 2", generator="ace-step-command", duration_seconds=10)
    job2 = job_service.create_job(req2)
    
    captured_command.clear()
    gen_service.run_job(job2.id)
    job2_record = job_service.get_required(job2.id)
    
    assert job2_record.status == "SUCCEEDED", f"Job should succeed, but got {job2_record.status}: {job2_record.error}"
    print("Test 2 Passed: Job succeeds when ACE usable.")
    
    # 4. Verify version_details
    assert "aceRuntimeConfig" in job2_record.version_details, "JobRecord.version_details missing aceRuntimeConfig"
    cfg = job2_record.version_details["aceRuntimeConfig"]
    assert cfg["lm_model"] == "mock-lm-0.6B"
    assert cfg["inference_steps"] == 12
    assert cfg["batch_size"] == 2
    assert cfg["offload_to_cpu"] is True
    assert cfg["device"] == "cuda"
    assert cfg["config_tier"] == "safe_recommended"
    assert cfg["profile_timestamp"] == "2026-06-27T00:00:00Z"
    print("Test 3 Passed: version_details.aceRuntimeConfig exists and has correct values on JobRecord.")
    
    media = media_store.get(job2_record.media_asset_id)
    assert "aceRuntimeConfig" in media.version_details, "MediaAsset.version_details missing aceRuntimeConfig"
    print("Test 4 Passed: version_details.aceRuntimeConfig exists on MediaAsset.")
    
    # 5. Verify command
    cmd_str = " ".join(captured_command)
    assert "--device cuda" in cmd_str
    assert "--lm mock-lm-0.6B" in cmd_str
    assert "--batch 2" in cmd_str
    assert "--steps 12" in cmd_str
    print("Test 5 Passed: Command correctly rendered injected values.")
    
    print("All tests passed successfully!")

if __name__ == "__main__":
    run_test()
