#!/usr/bin/env python3
"""Submit and poll quality experiment comparison generations."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
STYLE = "style_64dd8da29ffd4ddabc825405e37292b1"

PAIRS = [
    {
        "title": "Quality exp pair 1",
        "prompt": "Ambient shoegaze instrumental, dreamy reverb guitars, soft drums",
        "seed": 424242,
    },
    {
        "title": "Quality exp pair 2",
        "prompt": "Ethereal guitar wash, slow tempo, washed-out reverb, no vocals",
        "seed": 888001,
    },
    {
        "title": "Quality exp pair 3",
        "prompt": "Dark ambient bed, sparse distant drums, hazy guitars",
        "seed": 888002,
    },
    {
        "title": "Quality exp pair 4",
        "prompt": "Lush shoegaze instrumental, thick chorus guitars, gentle cymbals",
        "seed": 888003,
    },
    {
        "title": "Quality exp pair 5",
        "prompt": "Floating ambient instrumental, wide stereo guitars, soft pulse",
        "seed": 888004,
    },
]


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as resp:
        return json.load(resp)


def poll_job(job_id: str, timeout_s: int = 600) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        body = get(f"/api/jobs/{job_id}/status")
        status = body["status"]
        print(f"  poll {job_id} -> {status}")
        if status in ("SUCCEEDED", "FAILED", "TIMEOUT", "CANCELLED"):
            return get(f"/api/jobs/{job_id}")
        time.sleep(5)
    raise TimeoutError(f"job {job_id} timed out")


def generate_one(title: str, prompt: str, seed: int, styled: bool, lora_scale: float = 1.0) -> dict:
    payload = {
        "title": title + (" styled" if styled else " baseline"),
        "prompt": prompt,
        "lyrics": "[Instrumental]",
        "generator": "ace-step-command",
        "duration_seconds": 15,
        "seed": seed,
        "quality": "draft",
        "mode": "instrumental",
        "allow_fallback": False,
    }
    if styled:
        payload["style_version_id"] = STYLE
        payload["lora_scale"] = lora_scale
    created = post("/api/generate", payload)
    job_id = created["job_id"]
    print(f"submitted {payload['title']} job={job_id}")
    job = poll_job(job_id)
    j = job["job"]
    vd = j.get("version_details") or {}
    meta = (j.get("result") or {}).get("metadata") or {}
    return {
        "job_id": job_id,
        "media_id": f"media_{job_id}",
        "status": j["status"],
        "error": j.get("error"),
        "use_lora": vd.get("useLora"),
        "lora_scale": vd.get("loraScale"),
        "backend": vd.get("backend") or meta.get("backend"),
        "lora_load_succeeded": meta.get("loraLoadSucceeded"),
    }


def main() -> int:
    results = []
    for i, pair in enumerate(PAIRS, 1):
        print(f"\n=== pair {i} ===")
        baseline = generate_one(pair["title"], pair["prompt"], pair["seed"], styled=False)
        styled = generate_one(pair["title"], pair["prompt"], pair["seed"], styled=True, lora_scale=1.0)
        results.append(
            {
                "pair": i,
                "prompt": pair["prompt"],
                "seed": pair["seed"],
                "baseline": baseline,
                "styled": styled,
                "compare_url": (
                    f"/songs/compare.html?baseline_id={baseline['media_id']}&styled_id={styled['media_id']}"
                ),
            }
        )
    print("\n=== RESULTS ===")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
