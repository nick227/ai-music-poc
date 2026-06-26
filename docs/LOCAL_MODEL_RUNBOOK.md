# Local Model Runbook

1. Run app with default `.env`; confirm procedural generation works.
2. Install ACE-Step in a separate environment.
3. Create or locate an ACE inference script that accepts prompt/lyrics files and output path.
4. Set `ACE_ENABLED=true` and fill all `ACE_*` paths.
5. Visit `/api/model-status`.
6. Generate with `ace-step-command` and `allow_fallback=true` first.
7. Disable fallback only after a known-good command works.
