[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](README.md)
[![한국어](https://img.shields.io/badge/Language-한국어-red?style=for-the-badge)](./docs/README_KO.md)


<div align="center">
  <img src="assets/logo_banner.png" alt="Decepticon Logo">
</div>

<h1 align="center">Decepticon — Autonomous Red Team Framework</h1>

<div align="center">

<!-- GitHub License -->
<a href="https://github.com/PurpleAILAB/Decepticon/blob/main/LICENSE">
  <img src="https://img.shields.io/github/license/PurpleAILAB/Decepticon?style=for-the-badge&color=blue" alt="License: Apache 2.0">
</a>

<!-- GitHub Stars -->
<a href="https://github.com/PurpleAILAB/Decepticon/stargazers">
  <img src="https://img.shields.io/github/stars/PurpleAILAB/Decepticon?style=for-the-badge&color=yellow" alt="Stargazers">
</a>

<!-- GitHub Contributors -->
<a href="https://github.com/PurpleAILAB/Decepticon/graphs/contributors">
  <img src="https://img.shields.io/github/contributors/PurpleAILAB/Decepticon?style=for-the-badge&color=orange" alt="Contributors">
</a>

<br/>

<!-- Discord -->
<a href="https://discord.gg/TZUYsZgrRG">
  <img src="https://img.shields.io/badge/Discord-Join%20Us-7289DA?logo=discord&logoColor=white&style=for-the-badge" alt="Join us on Discord">
</a>

<!-- Website -->
<a href="https://purplelab.framer.ai">
  <img src="https://img.shields.io/badge/Visit%20Website-brightgreen?logo=vercel&logoColor=white&style=for-the-badge" alt="Visit Website">
</a>

<!-- Docs -->
<a href="https://purpleailab.mintlify.app">
  <img src="https://img.shields.io/badge/Docs-Philosophy%20%26%20Vision-8B5CF6?logo=bookstack&logoColor=white&style=for-the-badge" alt="Documentation">
</a>

</div>

---

> **Warning**: Do not use this project on any system or network without explicit authorization.
> You are solely responsible for your actions.

> **Note**: This is the `refactor` branch — a complete rewrite of Decepticon using the deepagents + LangGraph stack.
> For the previous version, see the [`main`](https://github.com/PurpleAILAB/Decepticon/tree/main) branch.

---

<details>
<summary><strong>Table of Contents</strong></summary>

- [What's New in 2.0](#whats-new-in-20)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [CLI Usage](#cli-usage)
- [Agent Hierarchy](#agent-hierarchy)
- [Skills Knowledge Base](#skills-knowledge-base)
- [Docker Infrastructure](#docker-infrastructure)
- [Configuration](#configuration)
- [Development](#development)
- [Contributing](#contributing)
- [Community](#community)
- [License](#license)

</details>

---

## What's New

Decepticon has been rewritten from the ground up — from a monolithic CLI to a **multi-agent orchestration framework**:

| Feature | v1 (main) | v2 (refactor) |
|---------|-----------|---------------|
| Agent Framework | LangChain ReAct | deepagents + LangGraph |
| Architecture | Single agent + MCP tools | Orchestrator + specialist sub-agents |
| Tool Execution | MCP servers (stdio/HTTP) | Docker sandbox with tmux sessions |
| Knowledge | Hardcoded prompts | 30+ progressive-disclosure skills |
| Context Management | None | Observation masking + output truncation |
| Autonomous Mode | None | Ralph loop (objective-driven iteration) |
| LLM Routing | Direct API calls | LiteLLM proxy with role-based routing |
| Auth | OAuth per-provider | API key via LiteLLM proxy |

## Architecture

```
                          ┌──────────────────────────┐
                          │     Decepticon CLI        │
                          │  (Rich terminal UI)       │
                          └────────────┬─────────────┘
                                       │
                          ┌────────────▼─────────────┐
                          │   Streaming Engine        │
                          │  (observation masking,    │
                          │   context compaction)     │
                          └────────────┬─────────────┘
                                       │
              ┌────────────────────────▼────────────────────────┐
              │            Decepticon Orchestrator              │
              │  (kill chain coordination, task() delegation)   │
              └──┬──────────┬──────────┬──────────┬────────────┘
                 │          │          │          │
          ┌──────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌───▼──────────┐
          │ Planner  │ │ Recon  │ │Exploit │ │ PostExploit  │
          │ Agent    │ │ Agent  │ │ Agent  │ │ Agent        │
          └──────────┘ └───┬────┘ └───┬────┘ └───┬──────────┘
                           │          │          │
                    ┌──────▼──────────▼──────────▼──────┐
                    │       Docker Sandbox (Kali)       │
                    │   tmux sessions · nmap · sqlmap   │
                    │   hydra · nikto · gobuster · ...  │
                    └───────────────────────────────────┘
```

**Key components:**

- **`decepticon/agents/`** — Agent factories using `create_deep_agent()` with middleware stacks
- **`decepticon/backends/docker_sandbox.py`** — Tmux-based command execution inside Docker
- **`decepticon/core/streaming.py`** — StreamingEngine with observation masking (old outputs compressed)
- **`decepticon/loop.py`** — Ralph loop: autonomous objective-driven iteration
- **`decepticon/ui/cli/`** — Rich-based terminal interface with agent-labeled output
- **`skills/`** — 30+ Markdown knowledge files with YAML frontmatter (progressive disclosure)

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Docker & Docker Compose

### 1. Clone & Install

```bash
git clone -b refactor https://github.com/PurpleAILAB/Decepticon.git
cd Decepticon

uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY and/or OPENAI_API_KEY
```

### 3. Start Infrastructure

```bash
# Core services: LiteLLM proxy + PostgreSQL + Kali sandbox
docker compose up -d --build

# (Optional) Demo victims for testing
docker compose --profile victims up -d
```

### 4. Run CLI

```bash
decepticon
```

## CLI Usage

The CLI starts in **Planning Agent** mode. Switch agents with slash commands:

```
you (planning): Generate an engagement plan for 192.168.1.0/24

/recon          — Switch to Reconnaissance Agent
/exploit        — Switch to Exploitation Agent
/postexploit    — Switch to Post-Exploitation Agent
/decepticon     — Switch to Orchestrator (autonomous delegation)
/plan           — Switch back to Planning Agent

/ralph          — Start autonomous Ralph loop (objective-driven)
/ralph status   — Check loop progress
/ralph resume   — Resume after interrupt

/compact        — Compress conversation context
/clear          — Reset conversation
/help           — Show all commands
/quit           — Exit
```

**Agent-labeled output** — always know which agent is speaking:

```
● planning: I'll generate the RoE and OPPLAN documents...
  ● skill (roe-template)

● decepticon: Delegating network recon to the recon agent...

  ▸ recon ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ┌──────────────────────────────────┐
  │ root@kali:/workspace             │
  │ $ nmap -sV -sC 192.168.1.0/24   │
  │ ...                              │
  └──────────────────────────────────┘
  ● recon: Found 3 hosts with open services...
  ◂ recon complete (45s) ━━━━━━━━━━━━━━━━━━
```

## Agent Hierarchy

### Decepticon Orchestrator
Top-level coordinator. Reads OPPLAN objectives, delegates to specialist sub-agents via `task()`, synthesizes results across kill chain phases. Recursion limit: 200.

### Planner Agent
Generates engagement documents: **RoE** (Rules of Engagement), **CONOPS** (Concept of Operations), **OPPLAN** (Operations Plan). No tools — document generation only.

### Recon Agent
Passive/active reconnaissance. Subdomain enumeration, port scanning, service detection, vulnerability scanning, OSINT. Tools: bash (in sandbox).

### Exploit Agent
Initial access via web attacks (SQLi, SSTI, command injection), AD attacks (Kerberoasting, ADCS abuse), credential attacks. Tools: bash (in sandbox).

### PostExploit Agent
Post-exploitation: credential access, privilege escalation, lateral movement, C2 management. Tools: bash (in sandbox).

## Skills Knowledge Base

Skills are Markdown files with YAML frontmatter, loaded on-demand via **progressive disclosure**:

```
skills/
├── recon/
│   ├── passive-recon/SKILL.md      # WHOIS, DNS, subfinder, crt.sh
│   ├── active-recon/SKILL.md       # nmap, service enum, vuln scanning
│   ├── web-recon/SKILL.md          # Directory brute, tech fingerprint
│   ├── cloud-recon/SKILL.md        # AWS/Azure/GCP enumeration
│   └── osint/SKILL.md              # OSINT techniques
├── exploit/
│   ├── web/SKILL.md                # SQLi, SSTI, XSS, command injection
│   └── ad/SKILL.md                 # Kerberoasting, ADCS, credential attacks
├── post-exploit/
│   ├── privilege-escalation/SKILL.md
│   ├── lateral-movement/SKILL.md
│   ├── credential-access/SKILL.md
│   └── c2/SKILL.md                 # Sliver C2 framework
├── shared/
│   ├── opsec/SKILL.md              # Operational security
│   ├── defense-evasion/SKILL.md    # AMSI bypass, AV evasion
│   └── workflow/SKILL.md           # Kill chain dependency graph
└── decepticon/
    ├── orchestration/SKILL.md      # Delegation patterns
    ├── engagement-lifecycle/SKILL.md
    └── kill-chain-analysis/SKILL.md
```

Only the `description` field from frontmatter is loaded initially. Full content is fetched when the agent decides it needs the skill — keeping the context window lean.

## Docker Infrastructure

### Core Services

| Service | Container | Purpose |
|---------|-----------|---------|
| LiteLLM Proxy | `decepticon-litellm` | LLM API gateway with model routing |
| PostgreSQL | `decepticon-postgres` | LiteLLM persistent storage |
| Kali Sandbox | `decepticon-sandbox` | Tool execution (nmap, sqlmap, hydra, ...) |

### Victim Infrastructure (Optional)

Start with `docker compose --profile victims up -d`:

| Service | Container | Purpose |
|---------|-----------|---------|
| DVWA | `decepticon-dvwa` | Web vulnerabilities (SQLi, XSS, Command Injection) |
| Metasploitable 2 | `decepticon-msf2` | Vulnerable Linux host (vsftpd, Samba, MySQL, ...) |

### Sandbox Tools

The Kali sandbox includes: `nmap`, `whois`, `dig`, `subfinder`, `curl`, `wget`, `hydra`, `sqlmap`, `nikto`, `smbclient`, `exploitdb`, `dirb`, `gobuster`, `netcat`, `python3`.

## Configuration

### LLM Models (`config/litellm.yaml`)

Role-based model routing through LiteLLM proxy:

```yaml
model_list:
  - model_name: recon-model        # Recon agent
    litellm_params:
      model: anthropic/claude-haiku-4-5-20251001
  - model_name: planning-model     # Planning agent
    litellm_params:
      model: anthropic/claude-haiku-4-5-20251001
  - model_name: exploit-model      # Exploit agent
    litellm_params:
      model: anthropic/claude-haiku-4-5-20251001
  - model_name: decepticon-model   # Orchestrator
    litellm_params:
      model: anthropic/claude-sonnet-4-20250514
```

### Application Config (`config/decepticon.yaml`)

```yaml
llm:
  mode: apikey
  proxy_url: http://localhost:4000
  roles:
    recon:
      model: recon-model
      temperature: 0.3
    planning:
      model: planning-model
      temperature: 0.4
    decepticon:
      model: decepticon-model
      temperature: 0.4

docker:
  sandbox_container_name: decepticon-sandbox
```

## Development

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Tests
pytest                                          # All tests
pytest tests/unit/core/test_config.py -k test   # Single test

# Code quality
basedpyright                                    # Type checking
ruff check .                                    # Lint
ruff format .                                   # Format
```

## Contributing

We welcome contributions! Whether you're adding new skills, improving agents, or fixing bugs:

1. Fork the repository
2. Create a branch (`git checkout -b feature/your-feature`)
3. Commit with clear messages
4. Open a Pull Request

**Ways to contribute:**

- **Skills**: Add offensive security knowledge to `skills/`
- **Agents**: Improve agent prompts and middleware stacks
- **Tools**: Extend sandbox tooling in `containers/sandbox.Dockerfile`
- **Testing**: Add unit/integration tests

## Philosophy & Vision

For a deeper look at Decepticon's philosophy, design principles, and where we're heading — check our **[documentation site](https://purpleailab.mintlify.app)**.

Topics covered include Vibe Hacking, the autonomous red team paradigm, context engineering for offensive agents, and how AI-driven security testing fits into the broader threat landscape.

## Community

Join our [Discord](https://discord.gg/TZUYsZgrRG) to connect with developers, share ideas, and collaborate on building the future of AI-powered red teaming.

## License

This repository is licensed under the [Apache-2.0 License](LICENSE).

---

## Star History

<a href="https://www.star-history.com/?repos=PurpleAILAB%2FDecepticon&type=date&logscale=&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/image?repos=PurpleAILAB/Decepticon&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/image?repos=PurpleAILAB/Decepticon&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/image?repos=PurpleAILAB/Decepticon&type=date&legend=top-left" />
 </picture>
</a>

![main](./assets/main.png)
