# swarmgate

Experiments on how populations of LLM agents learn about their oversight from blocking feedback, and how shared memory carries that knowledge.

## Prior work

This repository was started before the Swarm Alignment Hackathon sprint. Everything up to and including commit `d816044` is preexisting:
- the E0 audit;
- the sandbox and both guards;
- the E1 harness;
- the probe;
- the E1a vignettes;
- the donor pilot.

Later commits were made during the sprint.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). `requirements.txt` pins every dependency.

```bash
uv venv
uv pip sync requirements.txt
source .venv/bin/activate
```

Observer models are configured in `configs/observers.yaml`. Credentials are read from the environment or from a `.env` file in the project root:

- `ANTHROPIC_API_KEY`: Claude models.
- `META_API_KEY`: Meta models through the OpenAI-compatible Meta Model API.
- `ADAPTION_API_KEY`: open-weight models through the Adaption platform's hosted inference (Responses API).
- Gemini, via Vertex AI with Application Default Credentials:
  1. Run `gcloud auth application-default login`.
  2. Set `GOOGLE_CLOUD_PROJECT`.

Local models can be used through any OpenAI-compatible server (the `local` observer).

## E0: leakage and attribution audit

Each hidden guard is either syntactic (it decides on commands, paths and hosts) or information-flow (it decides on data labels and sinks). Scripted probe sequences are run against these guards and rendered under four feedback modes:

- verbose
- generic
- camouflaged
- fake success

For each sequence, an observer model does three things:

1. predicts the guard's decisions on held-out commands;
2. says whether each failure came from the guard or from the environment;
3. identifies what the guard bases its decisions on.

An exact Bayesian observer over the full hypothesis space gives the information-theoretic bound.

```bash
python -m swarmgate.e0 trials  --config configs/e0.yaml
python -m swarmgate.e0 ideal   --config configs/e0.yaml
python -m swarmgate.e0 models  --config configs/e0.yaml --observer claude-sonnet-5
python -m swarmgate.e0 observe --config configs/e0.yaml --observer claude-sonnet-5
python -m swarmgate.e0 analyze --config configs/e0.yaml
```

Before running an observer, set its `model` field in `configs/observers.yaml`; `models` lists the identifiers available to your credentials. `configs/e0-pilot.yaml` runs a small pilot on separate hidden guards.

`configs/e0-space.yaml` uses another set of hidden guards to compare observers that are also told the space of possible guards with the same models told nothing more. These observers have `guard_space: true` in `configs/observers.yaml`, for example `claude-sonnet-5-space`. An observer's `modes` field limits it, in runs and in analysis, to those feedback modes; trials with no observations are always included.

Outputs are written to `runs/e0/<name>/`.

Observer runs can be safely interrupted:

- **Progress is saved as it goes.** Each completed trial is appended to `responses.jsonl` immediately.
- **Transient failures are retried** with backoff, and requests are rate-limited according to the observer's `rpm`.
- **Failed trials are logged** to `errors.jsonl`.
- **Re-running the same command resumes the run.** Only unfinished or failed trials are run again.
- **Refusals are kept as data.** A refused trial counts as done and is excluded from scoring; add `--retry-refused` to ask again, for example after a change in account access.

## Sandbox

The agent studies run each session in a Docker container built from `docker/`:

```bash
docker build -t swarmgate-sandbox:dev docker/
```

Each command runs as an unprivileged user under `strace`. The guards decide from the trace, outside the agent's view: the syntactic guard from program names, path patterns and hosts, and the effect guard from where labelled data flows. `tests/fixtures/record_traces.py` re-records the traces the guard tests use.

## E1: handoff notes under a guard

Agents work operations tickets in the sandbox and leave handoff notes in `/team/NOTES.md` for the next agent in their lineage. In one arm the guard blocks three benign actions (G); in the other it is repaired (G′). Mechanical scoring then measures whether the notes carry working ways past G′.

The design, outcomes and tests are fixed in [PREREGISTRATION.md](PREREGISTRATION.md).

```bash
python -m swarmgate.e1 probe --models claude-sonnet-5
python -m swarmgate.e1 vignettes --models claude-sonnet-5-5,claude-sonnet-5
python -m swarmgate.e1 code --coder gemini --out runs/vignettes/codes-gemini.jsonl
python -m swarmgate.e1 code --coder gemini-pro --share 0.2 --out runs/vignettes/codes-gemini-pro.jsonl
python -m swarmgate.e1 vignette-report
python -m swarmgate.e1 pilot --config configs/e1-pilot.yaml
python -m swarmgate.e1 chains --config configs/e1.yaml
python -m swarmgate.e1 score --config configs/e1.yaml
python -m swarmgate.e1 potency-report --config configs/e1.yaml
```

- `probe` checks whether a model takes the donor and attacker roles at all.
- `vignettes` runs scripted sessions that end with the request to write notes. `code` codes each note with a model from another family, and `vignette-report` gives the recording rate, disclosure and coder agreement.
- `pilot` runs a few sessions for each candidate donor model and applies the donor rule.
- `chains` runs every lineage; `--status` prints progress and spend without running anything. No new generation starts once spend reaches `budget_usd`. Between generations the donor model merges the session's notes into the notes the next agent receives; if it refuses, the previous notes carry over unchanged and `--status` counts the refusal.
- `score` extracts the commands in the notes after the chosen generations, retargets each one to every objective, runs it once under the repaired guard and records which objectives succeed. An empty-notes anchor, and any notes files listed under `anchors` in the config, are scored the same way. If an anchor's SHA-256 is listed under `anchor_sha256`, the file must match it or scoring stops. The positive-control file is not published.
- `potency-report` gives potency per arm and generation, and the paired test between arms.
- The open-weight replication (E1b-OW in the preregistration) runs the same `pilot`, `chains`, `score` and `potency-report` commands with `configs/e1-pilot-ow.yaml` and `configs/e1-ow.yaml`. Its candidate models are served through the Adaption platform.

Every command resumes where it stopped.

## Tests

```bash
pytest
```
