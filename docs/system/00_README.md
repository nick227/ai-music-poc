# AI Music Studio Planning Pack

This pack defines the product and implementation direction for building a full AI Music Studio around the current ACE-Step music generation POC.

## Documents

1. `01_PM_BRIEF.md` — product framing, goals, phases, and success criteria.
2. `02_ARCHITECTURE_PROPOSALS.md` — multiple architecture options and recommendation.
3. `03_LEAN_USER_REQUIREMENTS.md` — concise user requirements for the MVP.
4. `04_DATA_AND_PIPELINE_PROPOSAL.md` — taxonomy, media, pipeline, version, and schema proposal.
5. `05_CODE_SURFACE_BEST_PRACTICES.md` — declarative model-first code surface standards.
6. `06_CODEX_INSTRUCTION.md` — focused prompt for Codex.
7. `07_ANTIGRAVITY_INSTRUCTION.md` — focused prompt for Antigravity/Claude.
8. `08_CURSOR_INSTRUCTION.md` — focused prompt for Cursor.

## Working product thesis

The current ACE-Step generator POC becomes the model runtime seed inside a larger AI Music Studio.

The Studio is primarily:
- audio media management,
- category/concept taxonomy,
- generated song history,
- review/evaluation,
- version tracking,

with fine-tune/training runs as the downstream 20 percent of the platform.
