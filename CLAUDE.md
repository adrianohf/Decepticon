# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Decepticon 2.0 is an AI-powered autonomous red team testing framework (Python 3.13+). LLM agents execute security reconnaissance objectives inside a Docker Kali Linux sandbox. The autonomous loop ("Ralph") reads an operations plan, spawns a fresh agent per objective, executes via bash in the sandbox, and persists findings across iterations through files on disk (not agent memory).

## Commands

```bash
uv venv && source .venv/bin/activate  # Create/activate virtual environment
uv pip install -e ".[dev]"            # Install with dev dependencies
pytest                                 # Run tests (asyncio auto mode)
pytest tests/unit/core/test_config.py -k test_name  # Single test
basedpyright                           # Type checking (NOT mypy)
ruff check .                           # Lint
ruff format .                          # Format
```

CLI entry points: `decepticon` (main), `decepticon-auth` (credential management), `decepticon-init` (first-run setup).

## Architecture

**Two LLM modes** configured in `config/decepticon.yaml`:
- `apikey`: LiteLLM routes to any backend using API keys (default)
- `oauth`: Subscription-based OAuth (Claude Pro/Max, ChatGPT Plus, GitHub Copilot) with auto-refresh via `decepticon/auth/`

**Agent construction** (`agents/recon.py`, `agents/planner.py`): Both use `create_agent()` (not `create_deep_agent()`) with an explicit middleware stack: SkillsMiddleware → FilesystemMiddleware → SummarizationMiddleware → PromptCachingMiddleware → PatchToolCallsMiddleware. Recon agent has bash tool; planner agent has no tools (document generation only).

**Ralph loop** (`loop.py`): Loads `opplan.json` from disk each iteration → picks next pending objective → builds iteration prompt with RoE guard rails + previous findings → spawns fresh recon agent (clean context) → parses OBJECTIVE PASSED/BLOCKED signal → updates opplan status → appends to `findings.txt`.

**Engagement document hierarchy** stored in `/workspace/engagements/<slug>/`:
- `roe.json` — Rules of Engagement (scope constraints, checked every iteration)
- `conops.json` — threat actor profile, kill chain
- `opplan.json` — discrete objectives with acceptance criteria (drives Ralph)
- `findings.txt` — append-only cross-iteration memory

**Sandbox** (`backends/docker_sandbox.py`): `DockerSandbox` wraps `docker exec` with tmux session management. Named sessions allow parallel scans. PS1 polling detects command completion. Stall detection after 10s of no output change.

**Streaming** (`streaming.py`): `StreamingEngine` runs the agent and applies observation masking — tool outputs older than 3 turns and >5K chars are replaced with summaries. Defines `UIRenderer` protocol implemented by `CLIRenderer`.

## Context Engineering Conventions

This codebase is designed around controlling LLM context consumption:

1. **Observation masking** — old verbose tool outputs replaced with summaries in-place
2. **Output offloading** — bash outputs >15K chars saved to `/workspace/.scratch/` files, summary returned
3. **Output truncation** — large outputs keep 60% head + 40% tail, middle discarded
4. **Fresh agent per iteration** — no accumulated context across Ralph iterations
5. **Progressive skill disclosure** — only SKILL.md frontmatter loaded initially, full content on-demand
6. **System prompts use XML-tagged sections** (`<IDENTITY>`, `<CRITICAL_RULES>`, `<ENVIRONMENT>`, etc.)

## Code Conventions

- **Pydantic v2 everywhere**: Config uses `BaseSettings` with `env_prefix="DECEPTICON_"`. All schemas, auth types use Pydantic models. Enums use `StrEnum`.
- **Logging**: `from decepticon.core.logging import get_logger; log = get_logger("module.sub")`
- **Imports**: Public API re-exported through `__init__.py`. Internal code uses absolute imports. `from __future__ import annotations` in files with complex type hints.
- **Ruff**: line-length 100, target py313, select E/F/I/W, ignore E501.
- **Skills**: Markdown files in `skills/` with YAML frontmatter (`name`, `description`). The `description` drives progressive disclosure.

## Key Directories

- `decepticon/auth/providers/` — OAuth implementations per LLM provider
- `decepticon/ui/cli/` — Rich-based terminal UI (console, renderer, startup animation)
- `skills/` — Markdown knowledge base injected via SkillsMiddleware
- `reference/` — Read-only source code of related projects (not part of build)
- `config/decepticon.yaml` — Default config file
- Credentials: `~/.config/decepticon/auth.json` (mode 0600)
