# Objective Decomposition Rules

## Rule 1: One Objective = One Context Window

Every objective must be completable by a fresh agent instance in a single iteration. If you're unsure, it's too big — split it.

**Too big (split):**
- "Perform complete reconnaissance" → Split into passive, active, synthesis
- "Scan all ports on all targets" → Split by target group or port range

**Right size:**
- "Enumerate subdomains using passive sources"
- "Port scan top 1000 on 10.0.1.0/24"
- "Run nuclei on live web hosts"

## Rule 2: Kill Chain Phase Ordering

Objectives are ordered by phase, then by dependency within each phase:

```
recon (priority 1-N)
  → passive before active
  → DNS before port scan
  → port scan before service enumeration
  → service enum before vuln scan
weaponize (priority N+1...)
  → based on recon findings
deliver → requires weaponize output
exploit → requires deliver success
install → requires exploit success
c2 → requires install success
exfiltrate → requires c2 channel
```

## Rule 3: Mandatory Acceptance Criteria

Every objective MUST include these three types:

1. **Scope check:** "All targets verified against roe.json in-scope list"
2. **OPSEC check:** At least one OPSEC criterion (rate limit, timing, UA)
3. **Output persistence:** "Results saved to /workspace/..." with specific path

## Rule 4: Verifiable Criteria Only

Every acceptance criterion must be mechanically checkable.

**Bad:** "Thorough reconnaissance achieved", "Good coverage", "Comprehensive results"
**Good:** "subfinder results saved to /workspace/recon/subfinder.txt", "Scan rate ≤ 10 req/sec"

## Rule 5: MITRE ATT&CK Mapping

Every objective references its primary technique:

| Activity | Technique |
|---|---|
| Passive DNS | T1596.001 |
| WHOIS | T1596.002 |
| CT logs | T1596.003 |
| Active port scan | T1595.001 |
| Vulnerability scan | T1595.002 |
| Web fuzzing | T1595.003 |
| OS fingerprinting | T1592.001 |
| Service version detection | T1592.002 |
| Search engines | T1593.002 |
| Exploit public app | T1190 |
| Phishing | T1566.001 |

## Rule 6: Risk Level Assignment

| Risk Level | When to Use | Examples |
|---|---|---|
| low | Passive, no target interaction | WHOIS, DNS via public resolvers, OSINT |
| medium | Active scanning within scope | Port scan, httpx probing, fuzzing |
| high | Exploitation attempts | Metasploit, manual exploit, credential testing |
| critical | Service disruption risk | Buffer overflow, DoS-adjacent tests |

## Validation Checklist

Run through before finalizing the OPPLAN:

- [ ] Every objective fits in one context window
- [ ] Kill chain phase ordering respected
- [ ] No objective targets out-of-scope assets
- [ ] Every objective has scope check criterion
- [ ] Every objective has OPSEC check criterion
- [ ] Every objective has output persistence criterion
- [ ] MITRE technique mapped for each objective
- [ ] Priority numbers are sequential (1, 2, 3...) with no gaps
- [ ] Risk levels assigned per the table above
- [ ] `branch_name` follows convention: `engage/<client>-<type>-<date>`
- [ ] `threat_profile` field summarizes threat actor in one sentence
