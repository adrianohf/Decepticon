# Decepticon Documentation Index

Decepticon은 AI 기반 자율 Red Team 에이전트로, 컨텍스트 엔지니어링과 스킬 시스템을 활용하여 자동화된 보안 테스트를 수행한다. 궁극적 목표는 Red Team + Blue Team 협업 체계를 통한 "공격적 백신(Offensive Vaccine)" 구축.

---

## 디렉터리 구조

```
docs/
├── INDEX.md
├── architecture/                    # 에이전트 내부 아키텍처
│   └── context-engineering.md
├── design/                          # 설계 결정 / 기술 방향
│   ├── opplan-middleware.md
│   └── single-bash-and-graphdb.md
├── red-team/                        # Red Team 도메인 지식
│   ├── operations.md
│   ├── recon-methodology.md
│   ├── tools-techniques.md
│   └── ai-red-teaming.md
└── reference/                       # 외부 프레임워크 및 레퍼런스 분석
    ├── deepagents-framework.md
    ├── langchain-integration.md
    ├── anthropic-cybersecurity-skills.md
    ├── nanoclaw-architecture.md
    ├── nanobot-architecture.md        # NEW
    ├── agent-loop-patterns.md         # NEW
    ├── decepticon-ralph-loop-design.md # NEW
    ├── patterns-for-decepticon.md
    └── skill-format-spec.md
```

---

## architecture/ — 아키텍처 문서

| 문서 | 내용 | 참조 시점 |
|------|------|----------|
| [context-engineering.md](architecture/context-engineering.md) | 컨텍스트 윈도우 관리, observation masking, progressive disclosure, 메모리 전략 | 에이전트 내부 구조 작업 시 |

## design/ — 설계 문서

| 문서 | 내용 | 참조 시점 |
|------|------|----------|
| [opplan-middleware.md](design/opplan-middleware.md) | OPPLAN 미들웨어 설계/트레이드오프/동시성 제약 | OPPLAN 도구 확장/수정 시 |
| [single-bash-and-graphdb.md](design/single-bash-and-graphdb.md) | single-bash 철학, Neo4j 백엔드 마이그레이션, Security-AGI 방향성 | 공격 실행 표면/그래프 저장소 설계 시 |

## red-team/ — Red Team 도메인 문서

| 문서 | 내용 | 참조 시점 |
|------|------|----------|
| [operations.md](red-team/operations.md) | Red Team vs Pentest 구분, 14단계 라이프사이클, 규제 프레임워크(TIBER-EU/DORA/NIST), Purple Team, 성숙도 모델, 역량 갭 분석 | 에이전트 확장 로드맵/전략 수립 시 |
| [recon-methodology.md](red-team/recon-methodology.md) | MITRE ATT&CK TA0043 매핑, 도구 인벤토리, passive/active 정찰 워크플로우 | 정찰 스킬 작성/수정 시 |
| [tools-techniques.md](red-team/tools-techniques.md) | ATT&CK 전체 킬 체인(TA0001~TA0040) 도구/기법: C2, Persistence, PrivEsc, Evasion, AD 공격 체인, Cloud Red Team | 새 에이전트/스킬 구현 시 |
| [ai-red-teaming.md](red-team/ai-red-teaming.md) | AI 자율 공격 에이전트(PentestGPT, ATLANTIS, Buttercup), DARPA AIxCC, 아키텍처 패턴, 가드레일, CART | 아키텍처 의사결정/AI 에이전트 설계 시 |

## reference/ — 프레임워크 및 레퍼런스 분석

| 문서 | 내용 | 참조 시점 |
|------|------|----------|
| [deepagents-framework.md](reference/deepagents-framework.md) | DeepAgents SDK: create_deep_agent(), 미들웨어 스택, 백엔드, 스킬, 서브에이전트 시스템 | 에이전트 구현/확장 시 |
| [langchain-integration.md](reference/langchain-integration.md) | LangChain v1.0+ & LangGraph: 의존성, ChatModel, Tool, 상태 관리, 프로바이더 라우팅 | LLM/도구 연동 작업 시 |
| [anthropic-cybersecurity-skills.md](reference/anthropic-cybersecurity-skills.md) | 734+ 사이버보안 스킬 라이브러리 분석, 카테고리별 우선순위, 임포트 전략 | 스킬 확장 시 |
| [nanoclaw-architecture.md](reference/nanoclaw-architecture.md) | NanoClaw/OpenClaw 아키텍처: 컨테이너 격리, IPC, Task Scheduler, Group Memory | 샌드박스/오케스트레이션 작업 시 |
| [skill-format-spec.md](reference/skill-format-spec.md) | Decepticon 스킬 포맷 명세: YAML frontmatter, 본문 구조, 작성 가이드, 임포트 체크리스트 | 새 스킬 작성 또는 외부 스킬 임포트 시 |
| [nanobot-architecture.md](reference/nanobot-architecture.md) | Nanobot: AgentLoop, 이중 메모리, SubagentManager, 토큰 기반 통합 | 에이전트 루프/메모리 설계 시 |
| [agent-loop-patterns.md](reference/agent-loop-patterns.md) | 에이전트 루프 교차 분석: deepagents, Sisyphus, NanoClaw, OpenClaw, Nanobot | Ralph loop 설계/구현 시 |
| [decepticon-ralph-loop-design.md](reference/decepticon-ralph-loop-design.md) | Decepticon Ralph loop 아키텍처 설계: 이중 루프, 상태 관리, CLI 통합, 마이그레이션 경로 | Ralph loop 구현 시 |
| [patterns-for-decepticon.md](reference/patterns-for-decepticon.md) | 레퍼런스 프로젝트들에서 추출한 교차 패턴: 격리, 오케스트레이션, 메모리, 스킬 표준화 | 아키텍처 의사결정 시 |

---

## Reference Repositories

`reference/` 디렉터리에 클론된 외부 프로젝트:

| 레포지토리 | 관련도 | 용도 |
|-----------|--------|------|
| `deepagents/` | **CRITICAL** | 에이전트 프레임워크 (Decepticon 기반) |
| `anthropic-cybersecurity-skills/` | **HIGH** | 734+ 스킬 라이브러리 (agentskills.io 표준) |
| `nanoclaw/` | **HIGH** | 컨테이너 격리, IPC, 스케줄러 패턴 |
| `red-run/` | **HIGH** | 67개 공격 스킬 (Web/AD/PrivEsc/Evasion), Engagement State, Subagent 모델 |
| `openclaw/` | MEDIUM | NanoClaw의 원본, 대규모 아키텍처 참조 |
| `ralph/` | MEDIUM | Ralph loop 원본 참조 |
| `red-team-agent-skills/` | MEDIUM | LLM 에이전트 Red Teaming, 적응형 페이로드 |
| `aleister-skills/` | LOW | 추가 스킬 레퍼런스 |
| `openhands/` | LOW | 에이전트 프레임워크 참조 |
| `nanobot/` | **HIGH** | 경량 멀티채널 에이전트: AgentLoop, 이중 메모리, SubagentManager |
| `oh-my-opencode/` | **HIGH** | Sisyphus 3계층 오케스트레이션, 지혜 축적, 노트패드 시스템 |
| `opencode/` | LOW | 코딩 에이전트 참조 |
