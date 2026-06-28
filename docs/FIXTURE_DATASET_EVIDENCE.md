# Fixture Dataset Evidence

This covers the first evidence phases of the training and fine-tuning pipeline. Phase 1 proves that real WAV fixture audio can move through the Studio data path as categorized, training-eligible media and become an immutable frozen dataset. Phase 2 proves that the frozen dataset can feed a mock training run and produce Model Version lineage. Phase 3 proves that the frozen dataset can be materialized as an ACE-compatible training workspace and command contract. Phase 4 is an explicitly gated tiny real ACE fine-tuning smoke test. Phase 5 generates paired base-vs-trained ACE outputs for manual comparison.

Normal verification and pytest do not run ACE fine-tuning.

## What It Proves

- Fixture WAVs exist under `data/fixtures/audio/<slug>/`.
- Fixture media is imported into the app media store.
- Deterministic categories are created or reused.
- Media is marked reviewed, rights-confirmed, and training-eligible.
- Dataset Candidates are generated without lowering production thresholds.
- One candidate is frozen into a READY dataset.
- The frozen manifest includes media ids, file paths, durations, categories, total duration, `frozen_at`, and `manifest_hash`.
- Regenerating candidates does not mutate the frozen dataset manifest.

## Fixture Tags

- `bell`: Bell, Metallic, One Shot
- `chimes`: Chimes, Metallic, Ambient
- `ocean`: Ocean, Natural, Ambient, Loopable

Each primary fixture group targets `12` clips of about `5` seconds, giving `60` seconds per category.

## Commands

Generate and ingest fixture audio:

```bash
python scripts/ingest_fixture_audio.py --ensure-fixtures
```

Run the full Phase 1 proof:

```bash
python scripts/verify_fixture_dataset_flow.py
```

Run the Phase 2 mock training lineage proof:

```bash
python scripts/verify_mock_training_lineage_flow.py
```

Run the Phase 3 ACE workspace and command contract proof:

```bash
python scripts/verify_ace_training_contract_flow.py
```

Run the optional Phase 4 real ACE fine-tuning smoke test:

```bash
ACE_REAL_TRAINING_SMOKE=1 python scripts/verify_ace_real_training_smoke.py
```

Without `ACE_REAL_TRAINING_SMOKE=1` or `--run`, the Phase 4 script exits with a clear message and does not train.

Run the Phase 5 base-vs-trained generation comparison:

```bash
python scripts/verify_ace_model_version_comparison.py
```

The Phase 5 report proves paired generation succeeded and links trained outputs back to Model Version → TrainingRun → frozen Bell Dataset. It does not make an automatic quality claim.

The verification report is written under:

```text
data/experiments/fixture-dataset-flow/
data/experiments/mock-training-lineage-flow/
data/experiments/ace-training-contract-flow/
data/experiments/ace-real-training-smoke/
data/experiments/ace-model-version-comparison/
```

Generated fixture WAVs and reports live under `data/` and are not intended to be committed.
