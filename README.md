# Shift Notes

**Do guard false positives leave working attacks in agents' handoff notes?**

Oversight guards for language-model agents make mistakes. When a guard blocks a benign action, a benign agent may find another route and write it into the notes it hands to the next agent. If the guard is later repaired, those notes may still show a later reader the way past it.

This repository contains:
- **SwarmGate**, a traced sandbox for studying this;
- the `swarmgate` package, which runs every experiment;
- the preregistration and the deviations record;
- the analysis code behind every reported number.

## Findings

The experiment ran 416 agent sessions, with Claude Sonnet 5 and Qwen 3.5 397B as the agents.

1. **Over-blocking was real, and agents routed around it, even when told not to.**
   - Under the over-blocking guard, at least one action was denied in 46 to 48 of 52 sessions per cell, against 0 to 5 under the repaired guard.
   - Under the command-based guard, agents reached an over-blocked object another way in 25 (Claude) and 17 (Qwen) of 52 sessions.
2. **The notes recorded the workarounds and kept them.**
   - By the last shift, 11 of 13 Claude lineages and 10 of 13 Qwen lineages had a workaround recipe in their notes, every one labelled as a way around the reviewer. Under the repair, none did.
   - A recipe present after one shift was still there after the next in 27 of 29 cases (Claude) and 20 of 20 (Qwen).
3. **Rerunning the notes' commands found no attack.**
   - Every chain notes file scored 0 of 8 protected objectives under the repaired guard. The positive control scored 8 of 8 under the command-based guard.
   - The preregistered primary hypothesis (H1) and its open-weight replication (H1-OW) are not supported.
   - The notes held about one runnable command per file. The knowledge was in prose.
4. **A willing reader turned the notes into working attacks.** A reader model got one notes file and one objective and was asked for one command. That command was run under the repaired command-based guard. With Gemini 3.1 Pro as the reader:

   | Notes given to the reader | Shared-principle success |
   |---|---|
   | No notes | 0.08 (1 of 12) |
   | Positive control | 0.75 (9 of 12) |
   | Claude, over-blocked arm | **0.58** (90 of 156; 12 of 13 lineages) |
   | Claude, repaired arm | 0.02 (3 of 156) |
   | Qwen, over-blocked arm | **0.11** (17 of 156) |
   | Qwen, repaired arm | 0.01 (1 of 156) |

   - For Claude's notes, the paired difference between arms is 0.56 (bootstrap 95% CI 0.40 to 0.70, one-sided sign-flip p = 0.0002).
   - For Qwen's notes it is 0.10 (CI 0.02 to 0.20, p = 0.047).
5. **The reader decides.**
   - Claude Sonnet 5, as the reader, declined 44 to 77 percent of trials when given chain notes, and succeeded in 1 of 156 with either donor's over-blocked notes.
   - Gemini 3.1 Pro declined 11 to 30 percent.

**Takeaway:** guard false positives teach agents where the guard is loose, and shared memory keeps that lesson after the fix. Repairing a false positive should come with a review of what the team's notes say about it.

**Scope:**
- These results hold for one guard exemplar per class, two donors and two readers.
- The reader battery was run after the chains and is exploratory; `DEVIATIONS.md` records its design, which was fixed before any output was seen.
- The taint-guard class could not be interpreted, because its positive control passed neither measure.

## Method

### Testbed

- **Sandbox.** Each session runs in a Docker container with no network. The container holds a small service's workspace: configs, docs, logs, a secrets directory and a vault. It also has the ops tools `ticket`, `svc`, `bundle` and `artifact`, and internal hosts served by a stub server. Every secret holds a fresh canary in every session.
- **Mediator.** It runs each command as an unprivileged user under `strace` and builds per-process events from the trace. The guard decides from those events, outside the agent's view. A denial rolls the workspace back and returns "Tool call not approved."
- **Two guard classes.**
  - **Command-based (SYN):** blocks a reader program on a protected path pattern, a network program to a host outside the allowlist, or an upload of a protected path.
  - **Effect (process-level taint):** a process that reads labelled data taints what it writes, and labelled data may not reach the agent's output or any socket.
- **Over-blocking and repair.** In each class, the variant G wrongly blocks three benign actions that the tickets need: reading the credentials template, reading the masked token-refresh log, and attaching a debug bundle that contains the template. The variant G′ repairs exactly those, by content hash, and decides every forbidden action as G does.

### Design

- **Sessions.** Each session gives one agent two tickets and one `shell` tool, with at most 40 tool calls. The system prompt states the team policy and asks the agent to treat a denial in good faith rather than route around it.
- **Handoff.** The agent reads `/team/NOTES.md` at the start and writes session notes at the end. The donor model merges them into one file of at most 500 words for the next shift, and that file is the only state carried forward.
- **Arms.** A1 runs every shift under G; A4 runs every shift under G′.
- **Lineages.** Each arm has 13 lineages of 4 shifts in each guard class, yoked by task schedule, with each of two donors.
- **Preregistration.** The design, outcomes and tests are frozen in [PREREGISTRATION.md](PREREGISTRATION.md). Every departure is recorded in [DEVIATIONS.md](DEVIATIONS.md).

### Measures

- **Mechanical potency (preregistered primary).** Extract every command in the final notes, retarget it to 8 protected objectives (4 exact, 4 shared-principle), and run each variant once under G′.
- **Reader battery (exploratory).** A reader model gets one notes file and one objective, three times per objective, and is asked for one command. That command runs once under G′. The readers are Claude Sonnet 5 on both classes, and Gemini 3.1 Pro on the command-based class.
- **Notes coding (exploratory).** DeepSeek V4 Flash and Gemini 3.8 Flash code every merged notes file. The main codes are a workaround recipe and a bypass label. The two coders agree with kappa 0.83 for a recipe and 0.95 for a label.
- **Anchors.** An empty notes file, and an investigator-written positive control. The positive control is pinned by SHA-256 and withheld from the repository because it describes working routes past the toy guard.

## Prior work

This repository was started before the Swarm Alignment Hackathon sprint. Everything up to and including commit `d816044` is preexisting:
- the E0 audit;
- the sandbox and both guards;
- the E1 harness;
- the probe;
- the E1a vignettes;
- the donor pilot.

Later commits were made during the sprint.

## Repository layout

- `src/swarmgate/sandbox/`: the container, the traced mediator, trace parsing, the workspace and both guards.
- `src/swarmgate/e1/`: the agent harness, tickets, chains, mechanical scoring, the reader battery, notes coding and the reports.
- `src/swarmgate/e0/`: the E0 leakage and attribution audit.
- `src/swarmgate/llm.py`: model clients (Anthropic, Vertex Gemini, OpenAI-compatible, Adaption).
- `configs/`: run configurations and model specifications.
- `docker/`: the sandbox image.
- `tests/`: unit tests, including guard decisions on recorded traces.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). `requirements.txt` pins every dependency.

```bash
uv venv
uv pip sync requirements.txt
source .venv/bin/activate
```

Observer models are configured in `configs/observers.yaml`. Credentials are read from the environment or from a `.env` file in the project root:

- `ANTHROPIC_API_KEY`: Claude models. A spec's `api_key_env`, or a command's `--api-key-env`, can name another variable. Set `ANTHROPIC_WORKSPACE_ID` if the key is not scoped to a workspace.
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

Agents work operations tickets in the sandbox and leave handoff notes in `/team/NOTES.md` for the next agent in their lineage. In one arm the guard blocks three benign actions (G); in the other it is repaired (G′). Mechanical scoring, the reader battery and the notes coding then measure what the notes carry.

```bash
python -m swarmgate.e1 probe --models claude-sonnet-5
python -m swarmgate.e1 vignettes --models claude-sonnet-5-5,claude-sonnet-5
python -m swarmgate.e1 code --coder gemini --out runs/vignettes/codes-gemini.jsonl
python -m swarmgate.e1 code --coder gemini-pro --share 0.2 --out runs/vignettes/codes-gemini-pro.jsonl
python -m swarmgate.e1 vignette-report
python -m swarmgate.e1 pilot --config configs/e1-pilot.yaml
python -m swarmgate.e1 chains --config configs/e1.yaml
python -m swarmgate.e1 calibrate --config configs/e1.yaml
python -m swarmgate.e1 score --config configs/e1.yaml
python -m swarmgate.e1 potency-report --config configs/e1.yaml
python -m swarmgate.e1 chain-report
python -m swarmgate.e1 battery --anchors-only
python -m swarmgate.e1 battery
python -m swarmgate.e1 battery --reader gemini-pro --kinds syn --out runs/battery-gemini
python -m swarmgate.e1 battery-report
python -m swarmgate.e1 notes-code --coder deepseek-v4-flash
python -m swarmgate.e1 notes-code --coder gemini
python -m swarmgate.e1 notes-code-report --second codes-gemini.jsonl
python -m swarmgate.e1 hand-bundle
python -m swarmgate.e1 hand-report
python -m swarmgate.e1 export-tables
```

- `probe` checks whether a model takes the donor and attacker roles at all.
- `vignettes` runs scripted sessions that end with the request to write notes. `code` codes each note with a model from another family, and `vignette-report` gives the recording rate, disclosure and coder agreement.
- `pilot` runs a few sessions for each candidate donor model and applies the donor rule.
- `chains` runs every lineage; `--status` prints progress and spend without running anything. No new generation starts once spend reaches `budget_usd`. Between generations the donor model merges the session's notes into the notes the next agent receives; if it refuses, the previous notes carry over unchanged and `--status` counts the refusal.
- `calibrate` checks the guard variants, the legitimate routes and the naive objectives on seeds separate from the chains, and scores the positive control.
- `score` extracts the commands in the notes after the chosen generations, retargets each one to every objective, runs it once under the repaired guard and records which objectives succeed. An empty-notes anchor, and any notes files listed under `anchors` in the config, are scored the same way. If an anchor's SHA-256 is listed under `anchor_sha256`, the file must match it or scoring stops. The positive-control file is not published.
- `potency-report` gives potency per arm and generation, and the paired test between arms.
- `chain-report` gives, per donor, class and arm: denials, workarounds under G, ticket completion, refusals, malformed calls, final notes that mention a denial, and candidate commands. It also counts, per shift, the sessions that were denied, were denied on an over-blocked object, and reached such an object.
- `battery` runs the reader battery. A reader model gets each final NOTES.md (and each anchor) with each objective, three times, and is asked for one command. The command runs once under the class's G′. `--anchors-only` runs the anchors first, `--kinds` limits it to guard classes, and `--reader` and `--out` choose the reader and its output folder. `--lenient` also runs replies that are not a single command and keeps them apart. `battery-report` gives attempt rates, success, the anchor gate, the paired A1 − A4 test and success by objective.
- `notes-code` codes every merged NOTES.md for recipes, labels, caveats, denials, legitimate routes and stated guard rules. `--donor` and `--share` restrict it to a sample. `notes-code-report` gives the rates, retention across generations per arm and agreement with a second coder.
- `hand-bundle` draws a stratified sample of notes files and writes them under opaque ids for hand coding. `hand-report` gives the agreement between the hand codes and each model coder.
- `export-tables` writes per-session, per-file and per-trial tables to `results/`. They hold no notes text and no commands.
- The open-weight replication (E1b-OW in the preregistration) runs the same `pilot`, `chains`, `score` and `potency-report` commands with `configs/e1-pilot-ow.yaml` and `configs/e1-ow.yaml`. Its candidate models are served through the Adaption platform.

Every command resumes where it stopped.

## Tests

```bash
pytest
```
