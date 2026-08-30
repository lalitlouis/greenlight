# Security review — 2026-08-30

Security-focused review of the whole application (auth, access control, injection,
crypto, data exposure), following the `security-review` skill methodology: identify
→ filter false positives → keep only ≥8-confidence, concretely-exploitable findings.
Verified first-hand against `auth.py` and every route guard in `server.py`.

**Bottom line: the security fundamentals are sound.** One real vulnerability
(OAuth login CSRF / session fixation). No injection, no path traversal, no XXE, no
session forgery, no admin bypass, no deserialization sink reachable from a request.

---

# Vuln 1 — Login CSRF / session fixation: OAuth `state` is not bound to the browser

* **Severity: MEDIUM** · **Confidence: 8/10** · **Category: csrf / session-fixation**
* **Location:** `src/greenlight/auth.py:74-90` (`make_state`/`check_state`) +
  `src/greenlight/server.py:500-532` (`/auth/login`, `/auth/callback`)

**Description.** `make_state()` returns a signed *timestamp only* —
`base64(json({"ts": now})) + "." + hmac(...)` — with no per-browser nonce, and
nothing is stored in a cookie to compare the returned `state` against on callback.
`check_state()` accepts any `state` that verifies under `SESSION_SECRET` and is
<600s old. So `state` proves only "this server issued *a* state in the last ten
minutes," which any party obtains by starting their own login. The `gl_next`
cookie set at `/auth/login` is only a redirect target — `auth_callback` never
compares it to `state`.

**Exploit scenario.**
1. Attacker starts the Google flow themselves and captures a valid `code` (bound
   to the *attacker's* Google identity) and a valid `state` from their own
   redirect, without letting their browser consume the code.
2. Attacker delivers `https://scriptrisk.com/auth/callback?code=<attacker_code>&state=<valid_state>`
   to a victim (a link, or an auto-loading redirect). `SameSite=Lax` permits this
   top-level GET navigation.
3. The victim's browser hits the callback; `auth_callback` exchanges the
   attacker's code and sets the `sr_session` cookie for the **attacker's**
   identity (`server.py:524-531`). The victim is now silently signed into the
   attacker's account.
4. The victim uploads a screenplay. `create_run` records it under
   `owner = _require_signin(...)` = the attacker's `sub`
   (`save_owner`/`save_user_run`). The attacker later signs into their own
   account, sees the run in `/api/my/runs`, and reads the victim's full,
   unpublished Fountain source via `/api/script/{run_id}` — a concrete
   confidentiality breach of the victim's private screenplay.

**Preconditions (why MEDIUM, not HIGH):** the attacker must relay a *fresh*
single-use OAuth code to the victim before it expires, and the victim must upload
content while in the forced session. Both are standard login-CSRF assumptions and
practical, but they are real preconditions.

**Fix.** Bind `state` to the browser: at `/auth/login` generate a random nonce,
set it in an httponly `SameSite=Lax` cookie, and embed the same nonce inside
`state`; in `auth_callback` require the cookie nonce to equal the `state` nonce
(double-submit) in addition to the existing HMAC + TTL check. This is a small,
self-contained change to `auth.make_state`/`check_state` and the two auth routes.

---

## Out of formal scope — real but excluded by the review's own rules

These are genuine and worth fixing, but the security-review methodology explicitly
excludes their categories (resource-exhaustion / rate-limiting, and non-externally-
triggerable defense-in-depth). They already appear in `docs/REVIEW-2026-08-30.md`
(items A3, A8) and belong in the P0 remediation plan, not the formal vuln list.

- **Unauthenticated paid endpoints (A3).** `/api/fix`, `/api/whatif`,
  `/api/whatif/suggest` (`server.py:1617-1717`) lack `_require_signin` — an
  anonymous caller who knows the public demo run id can trigger paid
  Gemini/Pro calls, rate-limited only by a per-IP lane whose key is the
  client-supplied `X-Forwarded-For` (spoofable → effectively unlimited). Impact
  is **cost** against the $100 budget, not data access (other runs need a 48-bit
  id; demo data is already public), so it filters out as resource-exhaustion —
  but it is the single most valuable operational fix here: add `_require_signin`
  to those three routes, matching `/api/runs`.
- **Fail-open ownership check (A8).** `storage.load_owner` returns `None` on any
  exception; both ownership gates treat `None` as "anonymous, allowed." Not
  externally triggerable (needs an induced GCS fault) and the data is
  capability-public, so it is defense-in-depth — but make owner lookups fail
  *closed*: distinguish "no owner blob" from "lookup error," and deny on error.

## Rejected leads (checked, not vulnerabilities)

- **Session cookie forgery / HMAC / algorithm confusion / default secret** —
  HMAC-SHA256 over the exact payload, `hmac.compare_digest`, `exp` re-checked; no
  JWT `alg` field so no confusion surface; empty `SESSION_SECRET` *disables* auth
  (fails closed) rather than enabling forgery; `is_admin` re-derives from a
  Google-verified, audience-pinned `id_token` sealed in the signed cookie.
- **Path traversal** — `_safe_id` allowlists `[A-Za-z0-9_-]{1,64}`;
  `versioned_static` uses `resolve()` + prefix check; `record["script_path"]` is
  always server-written, never attacker-controlled.
- **XXE / upload deserialization** — `fdx.py` uses stdlib
  `xml.etree.ElementTree`, which does not resolve external entities (only the
  billion-laughs *DoS* class remains, excluded); PDF path is `pdfplumber` text
  extraction; no zip/pickle/yaml/eval/exec/`shell=True` reachable from any
  request path.
- **Admin bypass** — every `/api/admin/*` and `/admin` route is guarded by
  `auth.is_admin`/`_require_admin`; the 404-vs-403 inconsistency is a deliberate
  "don't advertise the surface" choice with no authz impact.
- **Invite bypass / OAuth open-redirect** — invite gate covers both run-creating
  paths; codes are a server-side env set redeemed per-`sub`; both `/auth/login`
  `next` and callback `dest` are constrained to same-site paths
  (`startswith("/")` and not `//`); Google enforces its own redirect_uri
  allowlist so a spoofed Host yields a redirect Google rejects.
- **Capability-model content endpoints** — `/api/records`, `/api/script`,
  `/api/binder`, `/api/revise` serve by 48-bit-random run id with no ownership
  re-check; this is the documented design and the ids are unguessable, so it is a
  conscious accept, not a vuln (worth revisiting if run-ids ever leak via
  Referer/proxy logs).
- **Server-rendered XSS** — no user input is interpolated into server-rendered
  HTML; CSP is `script-src 'self'` with no `unsafe-inline`; all model-generated
  strings render via `textContent` and every href passes `safeUrl`.
