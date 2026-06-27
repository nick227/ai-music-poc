import time
from pathlib import Path
from app.domain.models import GenerationRequest
from app.generators.procedural import ProceduralGenerator

def run_benchmark():
    generator = ProceduralGenerator()
    request = GenerationRequest(
        title="Benchmark",
        prompt="pop",
        lyrics="benchmark lyrics",
        duration_seconds=10.0,
        mode="song",
        structure="verse_chorus",
        quality="draft",
        seed=123,
    )
    start = time.time()
    generator.generate(request, Path("benchmark_out.wav"))
    end = time.time()
    print(f"Procedural 10s audio generated in {end - start:.4f} seconds")

if __name__ == "__main__":
    run_benchmark()
