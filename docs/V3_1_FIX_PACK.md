# V3.1 Fix Pack

V3.1 focuses on manual-test feedback from the procedural fallback.

## Changes

- Procedural fallback now uses distinct style profiles: disco, club, rap/trap, ambient, acoustic/indie, lo-fi, cinematic, pop, and default.
- Negative prompt text no longer influences style detection.
- UI label changed from `Lyrics` to `Lyrics / vocal guide`.
- UI helper clarifies that procedural mode does not sing words.
- Default UI generator selection now favors `procedural-v3` so ACE fallback is not hidden during local tests.
- ACE command foundation remains intact.

## Expected behavior

Procedural mode should now make different presets noticeably different. It still does not perform real text-to-singing. Real sung lyric behavior requires an ACE-Step/YuE-style model adapter.
