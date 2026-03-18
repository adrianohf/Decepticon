# Kill Chain Phase Templates

Select applicable phases based on engagement type and RoE scope.

## Full Kill Chain (All Phases)

| Phase | Description | Success Criteria | Typical Tools |
|-------|-------------|-----------------|---------------|
| recon | Passive + active intelligence gathering | Complete attack surface map | subfinder, nmap, httpx, nuclei |
| weaponize | Develop or select exploitation tools | Working exploit/payload ready | msfvenom, custom scripts |
| deliver | Deliver payload to target | Payload reaches target system | phishing, web exploit |
| exploit | Execute payload, gain initial access | Shell or credentials obtained | metasploit, manual exploit |
| install | Establish persistence | Survive reboot, re-access possible | implant, scheduled task |
| c2 | Command & control channel | Stable, covert C2 communication | Cobalt Strike, Sliver |
| exfiltrate | Extract target data | Proof of data access achieved | custom scripts, DNS exfil |

## Engagement Type → Phase Selection

### External Recon-Only
- Phases: `recon` only
- Focus: Attack surface mapping, no exploitation

### External Penetration Test
- Phases: `recon` → `weaponize` → `deliver` → `exploit`
- Focus: Find and prove exploitable vulnerabilities

### Full Red Team
- Phases: All 7 phases
- Focus: End-to-end adversary simulation

### Assumed Breach
- Phases: `install` → `c2` → `exfiltrate`
- Skip: `recon` through `exploit` (start with provided access)

### Internal Assessment
- Phases: `recon` → `exploit` → `install` → `c2` → `exfiltrate`
- Start from: Internal network position

## MITRE ATT&CK Tactic Mapping

| Kill Chain Phase | MITRE Tactic |
|---|---|
| recon | TA0043 Reconnaissance |
| weaponize | TA0042 Resource Development |
| deliver | TA0001 Initial Access |
| exploit | TA0002 Execution |
| install | TA0003 Persistence |
| c2 | TA0011 Command and Control |
| exfiltrate | TA0010 Exfiltration |
