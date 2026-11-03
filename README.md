# swarmgate

Experiments on how populations of LLM agents learn about their oversight from blocking feedback, and how shared memory carries that knowledge.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). `requirements.txt` pins every dependency.

```bash
uv venv
uv pip sync requirements.txt
source .venv/bin/activate
```

API keys are read from the environment or from a `.env` file in the project root:

- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `LLAMA_API_KEY`

Local models can be used through any OpenAI-compatible server (the `local` observer in the config).

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
python -m swarmgate.e0 models  --config configs/e0.yaml --observer claude-sonnet-5-5
python -m swarmgate.e0 observe --config configs/e0.yaml --observer claude-sonnet-5-5
python -m swarmgate.e0 analyze --config configs/e0.yaml
```

Set the `model` field of an observer in `configs/e0.yaml` before running it. `models` lists the identifiers available to your key. Outputs are written to `runs/e0/<name>/`.

## Tests

```bash
pytest
```
