# Deviations

The single record of deviations from the study plan.

## E0: Anthropic observer

- **Planned:** Claude Sonnet 5.5 at medium effort.
- **Used:** Claude Sonnet 5 (`claude-sonnet-5`) at medium effort, plus the same model at high effort as an added reasoning-budget arm.
- **Why:** Claude Sonnet 5.5 declined every E0 observer prompt with a `cyber` safeguard refusal before producing any output, under default safeguards and with Cyber Verification Program Defense Access. Claude Sonnet 5 answered every prompt. The refusals are kept in the run records and excluded from scoring.

## E0: guard-space arm

- **Planned:** observers see only the session log and a short framing of the task.
- **Added:** a separate set of hidden guards (`configs/e0-space.yaml`) on which Claude Sonnet 5 is run both with and without a description of the space of possible guards. The runs without it cover all four feedback modes at medium and high effort.
- **Narrowed:** with the description, the model reasons far longer, and under camouflaged and fake-success feedback its answers ran past the 16,000-token output limit. Runs with the description are therefore limited to no observations and to verbose or generic feedback, at medium effort first; high effort follows only if its answers fit the limit. This was decided before any of the arm's answers were scored.
- **Why:** in the main run, much of the readers' shortfall against the ideal observer was already present before any feedback, which points to a missing prior rather than slower learning. Describing the space tests this directly. The arm's predictions were fixed before it was run.
