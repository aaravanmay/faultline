# faultline — The Complete Platform Guide

*One file that explains the entire thing: what it is, how every part works, how to run it, how to deploy it, what was hardened, and where to take it next. Written 2026‑06‑07; updated same day with the visual‑QA, performance, and navigation fixes (see §9).*

---

## 0. TL;DR

**faultline = chaos engineering for AI agents.** It deliberately breaks an AI agent's tools (wrong/stale data, truncation, timeouts, 500s) and catches the **silent failures** — the moments the agent confidently does the wrong thing with **no error, no crash, all tests green**. Verdicts: **PASS** (resilient) / **SILENT‑WRONG** (the dangerous one — our headline) / **CRASH**.

It ships as two halves that meet over a token:
1. **Open‑source engine** (Python CLI + GitHub Action) that runs in the user's CI and tests their agent.
2. **Hosted platform** (this web app) that *receives* run results and shows resilience over time, regressions, and the exact silent failures caught.

The whole web stack is **static — no build step**: vanilla HTML/CSS/JS + GSAP + three.js + Lenis via CDN, with **Supabase** (Postgres + Auth + RLS) as the only backend.

---

## 1. Architecture at a glance

```
┌─────────────────────┐     pip install faultline       ┌──────────────────────┐
│  USER'S CI / LOCAL  │     faultline run --push        │   SUPABASE (backend) │
│  (the Python engine)│ ───────────────────────────────▶│  Postgres + Auth+RLS │
│  breaks tools,      │   POST rpc/ingest_run            │  ingest_run() RPC    │
│  classifies verdicts│   (project token in body)        │  runs, fault_results │
└─────────────────────┘                                  └──────────┬───────────┘
                                                                     │ supabase-js (anon key, RLS)
┌─────────────────────┐                                  ┌──────────▼───────────┐
│  MARKETING SITE     │  "Start free" / "Sign in"        │  HOSTED WEB APP      │
│  index.html (light) │ ────────── auth ────────────────▶│  /app/* (dark)       │
│  hero, fault lib,   │                                  │  overview, runs,     │
│  orbit, pricing     │                                  │  settings, etc.      │
└─────────────────────┘                                  └──────────────────────┘
```

- **Marketing site** = `site/index.html` (light theme). Sells the product.
- **Hosted app** = `site/app/*.html` (dark theme). The signed‑in product.
- **Backend** = Supabase. Schema/policies/functions in `site/sql/*.sql`.
- **Engine** = the Python package in the repo (`faultline/`) — already exists; the platform is the layer around it.

---

## 2. The marketing site (`site/index.html`)

Single file, light theme. Premium dev‑tool aesthetic with a seismic **fault‑line** motif.

### Sections (top → bottom)
1. **Hero** — leads with the *lie*: kicker "Your agent doesn't crash — it" + a giant fractured word **`LIES.`** (Clash Display) split along a glowing molten **fault rift** (a real three.js transmission‑glass object fused through the type), on a warm gradient‑mesh + film‑grain atmosphere. A **seismograph "page‑quake"** fires every ~10s (the word ruptures with a chromatic shudder — our signature, screen‑recordable beat). Below: value prop, CTAs, trust line, a copy‑able **`pip install faultline`** proof pill, then the dark dashboard product shot floating as a tilted glass tile. *(Leading with "it LIES" beat the earlier "WRONG."/"SILENT." — the active, ownable fear; per the investor + design teardown.)*
2. **Works‑with logos** — LangChain, smolagents, OpenAI, LangGraph, CrewAI, Anthropic.
3. **Problem** — "A 200 OK can still be completely wrong." + a terminal tile showing the **real output of `faultline run`** (the actual engine run: `wrong-number → SILENT-WRONG`, CRASHes, 0% resilience) — genuine proof, not a mock.
4. **How it works** — Break it → Catch it → Fix & gate it (3 cards).
5. **Fault library (LATERAL scroll)** — `#faultlib`: a pinned, horizontal‑scroll showcase of the 6 faults, ordered as a **detectability spectrum** (loud failures your tests catch on the left → silent killers on the right), each card showing the fault *and the agent's wrong reaction* (✓ caught / ✗ no error), with a labeled axis. Scrolls sideways as you scroll down (desktop + motion only; stacks vertically on mobile/reduced‑motion).
6. **Product** — "Catch regressions before they ship." + the dashboard tile.
7. **Scroll‑orbit (3D)** — `#orbit`: a dark section where a 3D crystal you **circle around** as you scroll, telling a **regression narrative** in 3 beats (Yesterday it passed → the model bumped → now it lies, resilience 94→71, PR failed) + a progress rail. Pinned/scroll‑bound on desktop; stacked beats on mobile. (Ties to the "it LIES" hero and the CI‑regression repositioning.)
8. **Why faultline** — the comparison table ("the layer everything else misses").
9. **Pricing** — Open source ($0) / Team (Free in beta) / Enterprise (Let's talk).
10. **FAQ** — working accordion.
11. **Closing** — "Find the silent failures before your users do." + footer.

### Motion system (all GSAP + Lenis)
- **Lenis** smooth scroll drives `ScrollTrigger.update` (one RAF loop).
- Per‑word headline reveals, scroll‑velocity skew, magnetic buttons, scroll‑spy nav.
- The **page‑quake** (seismograph spike → word rupture) on a loop.
- Two **pinned** scroll sections (lateral fault library, scroll‑orbit).
- Everything honors `prefers-reduced-motion` and falls back gracefully; **no horizontal scroll on mobile**.
- Two **three.js** scenes (hero fault‑rift, orbit crystal) use `MeshPhysicalMaterial` transmission/dispersion + `RoomEnvironment`; both have non‑WebGL fallbacks and are gated to desktop.

### Design tokens (light site)
`--bg:#F4F2EF · --surface:#FFF · --ink:#0B0D14 · --blue:#2563EB · hot‑blue #3B82F6/#7DD3FC · --silent(amber):#E0830C · --crash:#DC2B2B`. Fonts: **Clash Display** (display), **General Sans** (body), **JetBrains Mono** (code). Backups: `index-fracture-backup.html`, `index-v1-backup.html`.

---

## 3. Auth (`site/auth.js` + `site/supabase-config.js`)

- **Supabase Auth** via the supabase‑js CDN client. Config (your project URL + **public anon key**) lives in `supabase-config.js`.
- Methods: **email + password**, **magic link** (passwordless), **GitHub OAuth** (button auto‑hides until you enable the GitHub provider in Supabase).
- A polished **modal** (open via any `[data-auth="signin|signup"]` element; deep‑linkable via `/index.html#signin`). Fades via visibility/opacity.
- **Signed‑in nav state**: the marketing nav swaps "Sign in / Start free" → avatar + email + **Dashboard** + Sign out.
- **Redirect rule**: only a *real* sign‑in action routes to `/app/overview.html` (a flag set on submit / on oauth‑magic callback) — session‑restore does NOT eject you off the marketing page.
- The anon key is **public by design** (RLS protects data). Never put the `service_role` key in client code.

---

## 4. The hosted app (`site/app/*.html`)

Dark theme, **multi‑page** (no SPA/router — the browser is the router). Every page shares one spine.

### The spine — `app/app.js` (`window.fl`)
- **Client singleton** `fl.sb` (supabase‑js).
- **Auth gate** `fl.ready(cb)`: redirects to `/index.html#signin` if no session; **auto‑provisions a starter project** if the user has none (so the dashboard is ALWAYS reachable — no onboarding loop); injects the layout; then runs your render callback with `ctx` (session, user, orgId, orgs, projects, project).
- **Layout** (sidebar + topbar) is **inlined** in app.js (`LAYOUT` constant) and injected into `#shell` — no fetch (avoids a load‑race that previously blanked the nav).
- **Data helpers** (all RLS‑scoped): `getOverview, getRuns, getRun, getAgents, getFaults, getRegressions, resolveRegression, getTokens, mintToken, revokeToken, createProject`. `mintToken`/`createProject` throw on error.
- **Render utils**: `esc, rel, verdictClass/Label, runVerdict, agentColor, ring (SVG), sparkline (SVG), toast, copy, qs`.

### Pages
| Page | File | What it shows |
|---|---|---|
| Overview | `app/overview.html` | Resilience score ring + 7‑day trend, 4 KPI cards (silent caught / agents / last run / open regressions) w/ sparklines, 90‑day chart with regression markers, recent‑runs table. Rich **empty state** for new users. |
| Runs | `app/runs.html` | Full runs table, verdict filter pills, → run detail. |
| Run detail | `app/run.html?run=<id>` | The fault matrix (one row per fault: verdict, trial dots, "what happened", suggested fix), verdict banner, baseline note, "what faultline did NOT see" trust panel, compare‑to‑previous. |
| Agents | `app/agents.html` | Per‑agent resilience cards + sparklines. |
| Faults | `app/faults.html` | The 6‑fault library + per‑fault footprint (educational even at zero data). |
| Regressions | `app/regressions.html` | Open/resolved regressions; resolve/ignore (admin). |
| Settings | `app/settings.html` | Tabs: Project (rename + alert threshold, persists) · **Tokens** (mint once / revoke — real) · Team (invite = "coming soon") · Account (email + sign out). |
| Integrations | `app/integrations.html` | GitHub Action YAML, project‑token mint, CLI commands, "listening for first run". |
| Onboarding | `app/onboarding.html` | Light wizard: name project → mint token → install/run snippets → "Load demo data" / "Open dashboard". |

### Design system (dark app) — `app/app.css`
`--bg:#08090D · --panel:#0D0F15 · --accent:#3B82F6 · --cyan(pass):#38BDF8 · --silent(fail):#F59E0B · --crash:#6B7280`. Fonts: **Inter** (UI) + **JetBrains Mono** (numbers/code). Verdict color law everywhere: pass=cyan, SILENT‑WRONG=amber, crash=grey. Full component set (cards, table, pills, trial dots, score ring, buttons, inputs, code blocks, tabs, empty states, toasts, modal) — reused by every page.

---

## 5. The backend (Supabase) — `site/sql/`

**Run these once in the Supabase SQL editor, in order:**
1. **`schema.sql`** — tables (`profiles, organizations, org_members, projects, project_tokens, agents, runs, fault_results, regressions`), enums, **Row‑Level Security** (every table scoped to the caller's org membership via `is_org_member`/`has_org_role` SECURITY‑DEFINER helpers), a **signup trigger** (`handle_new_user` → creates a profile + personal org + owner membership), a **backfill** for users created before the trigger, and RPCs `create_org` / `create_project` / `create_project_token`.
2. **`ingest.sql`** — the `ingest_run(token, payload)` RPC (the ONE write CI may do): validates the project token by SHA‑256 hash, inserts the run + fault_results, derives regressions, all server‑side; granted to `anon`.
3. **`seed.sql`** *(optional)* — realistic demo data. (Easier path: sign in → onboarding → **"Load demo data"**, which seeds as your user via `app/seed.js`.) The browser seeder (`seed.js`) now produces a **fully self‑consistent** dataset: 11 runs of climbing resilience with a dip, a **6‑fault matrix on every run**, the **latest run a live wrong‑number regression (93→83%)**, and **3 regressions (1 open + 2 resolved)** — so every page (overview, run detail, agents, regressions) reconciles.

**Also in Supabase:** Authentication → URL Configuration → Site URL + Redirect URLs = `http://localhost:8791` (and your deployed URL). For frictionless dev, Authentication → Providers → Email → turn **off** "Confirm email" (re‑enable for production with custom SMTP).

### Data model ↔ engine
`runs` ⇄ one `chaos()`/`check()` execution (denormalised aggregates: resilience %, silent/crash counts, assertions). `fault_results` ⇄ `Result.rows[]` (`fault`, `verdict` `pass|fail|crash|inconclusive`, `detail`, `suggested_fix`, `trials[]`). The UI renders `fail` as "SILENT‑WRONG".

### CI ingest contract (how runs get in)
`POST https://<ref>.supabase.co/rest/v1/rpc/ingest_run` with headers `apikey: <anon>` and body `{ "p_token": "flt_live_…", "p_payload": { agent, trials, duration_ms, baseline_ok, git_*, results:[{fault,verdict,detail,suggested_fix,trials[]}] } }`. **Payload is metadata only — never agent prompts/data/code** (this is both the legal "never sees your data" guarantee and trivial since `rows` already exclude I/O). **This is implemented**: `faultline/report.py` serializes a `Result` to exactly this payload and POSTs it; `faultline run --push` (or any run with `FAULTLINE_TOKEN` set) fires it; `action.yml` passes the env through. Verified end-to-end against live Supabase.

---

## 6. Run it locally

```bash
cd site
./start.sh                 # or: python3 -m http.server 8791
open http://localhost:8791/index.html
```
- Marketing: `http://localhost:8791/index.html`
- App (after sign‑in): `http://localhost:8791/app/overview.html`
- **Verification** (what I used all night): a Python venv with Playwright at `faultline/.venv311/bin/python`. Headless Chromium = same engine as Chrome; run scripts in `site/junk/` to sign up test accounts (email‑confirm off) and walk flows. Note: software‑GL renders the 3D objects flat/gray — they're real glass on a GPU; judge composition in headless, quality on hardware.

---

## 7. Deploy (static site)

- It's a static site (all assets via CDN). Host on **Render Static Site / Vercel / Netlify** (free tiers).
- Push a **clean repo with only `site/`** — NEVER push the Antigravity monorepo (it has trading/.env secrets). `supabase-config.js` is safe to commit (anon key is public).
- After deploy: add the live URL to Supabase Site URL + Redirect URLs.

---

## 8. File map

```
faultline/
  CLAUDE.md                  engine context (the Python package + strategy)
  PLATFORM_GUIDE.md          ← this file
  faultline/                 the OSS engine (Python): runner, faults, detect, cli…
  site/
    index.html               marketing site (light) — hero, fault library, orbit, pricing, FAQ
    auth.js                  Supabase auth modal + session + signed-in nav
    supabase-config.js       YOUR project URL + anon key (public)
    start.sh, README.md      launcher + site docs
    mockups/
      dashboard.html         dark dashboard mock (used as product shot)
      terminal.html          terminal mock (product shot)
    sql/
      schema.sql             tables + RLS + trigger + backfill + RPCs   (run 1st)
      ingest.sql             ingest_run() RPC                            (run 2nd)
      seed.sql               optional demo data                          (run 3rd)
    app/
      app.css                dark app design system (shared)
      app.js                 the spine: client, auth gate, layout, data helpers
      overview.html runs.html run.html agents.html faults.html
      regressions.html settings.html integrations.html onboarding.html
      seed.js                "Load demo data" (browser-side seeding)
    OVERNIGHT_RUN_LOG.md     log of the hardening + rebuild session
    junk/                    screenshots + verification scripts (not part of the site)
```

---

## 9. What was hardened (this session)

Four parallel bug‑hunt agents stress‑tested every flow; all findings fixed + re‑verified:
- **Critical:** signed‑in users were force‑redirected off the marketing page (Supabase fires `SIGNED_IN` on session‑restore) → now only redirects on a real sign‑in action.
- **Dashboard unreachable** (the original symptom): two stacked bugs — the no‑project gate looped to onboarding, and a layout `fetch` race blanked the nav. Fixed: auto‑provision a project + inline the layout.
- Created the **missing `integrations.html`** (was 404 from 8 links).
- `createProject`/`mintToken` now throw on error; Settings "Save" persists; `getRun` uses `.maybeSingle()` + a UUID guard (no 400s) and fetches the previous run's faults; regressions are project‑scoped; onboarding reveal animation fires; mobile no longer overflows; modal fade, mobile‑menu z‑index + Escape, Docs link, Team price — all fixed.
- Verified: signup→dashboard works end‑to‑end, demo seed → 11 runs, **0 console errors across all app pages**, mobile clean.

### Visual‑QA + polish wave (rendered‑screenshot critique → fix → re‑verify)
Captured the *actual rendered pixels* (desktop scroll filmstrip + mobile + seeded dashboard) and ran 3 ruthless design critics (conversion / visual‑craft / product‑dashboard) + a 4th verification pass. Every finding was checked against the screenshot before fixing (≈half were screenshot‑crop artifacts, not real bugs). Real fixes, all re‑verified, 0 console errors:
- **Fault‑library cards** had a cavernous empty void — the intro `<h2>` rendered at 75px inside a 420px card → wrapped to 737px → flex‑stretched every sibling. Sized the intro heading for the card + gave cards a uniform `min‑height` → tidy 390px cards with a code block + green "✓ caught" / amber "✗ no error" reaction footer.
- **Scroll‑orbit text** was shrink‑wrapped (`position:absolute`, no width) so the body wrapped ~2 words/line and sat top‑anchored. Fixed: width + brighter body + pin‑proof vertical centering.
- **Data‑integrity bug:** the agent card showed a false "silent: 0" (it read only the *last* run) → now sums the agent's full history → "3 silent · 0 crash · 11 runs", plus a trend range ("80→83%").
- **Resilience chart** had no x‑axis → added date labels; the 30d/90d/1yr pills are now **functional** (filter the window), not decorative.
- **Run‑detail contradiction (the big one):** the fault matrix said "No faults injected" while the header claimed faults handled — the seed only wrote per‑fault rows for ONE run. **Rewrote `seed.js`** so every run gets a self‑consistent 6‑fault matrix (resilience / handled / silent / assertions / trial‑dots all derive from one source), and the **latest run is the wrong‑number regression (93→83%)** — the whole "it was climbing, then it lied" story now renders end‑to‑end on the run‑detail page.
- **Regressions page** enriched: 1 open + 2 resolved (the close‑loop), with the open‑count staying correct everywhere. "clean" fault‑tag → "all‑caught".

### Performance + navigation fixes (post‑review)
- **Orbit lag (your report):** the full‑screen transmission crystal was rendering *continuously — even when scrolled off‑screen* — at retina pixel ratio: a page‑wide GPU tax. Now it **renders on‑demand only while you scroll through that section**, pixel ratio capped 2→1.5, and the pinned scroll was cut 220%→130% (page ~1,150px shorter, far less dead space). The hero "LIES." shard already paused off‑screen, which is why only the orbit lagged.
- **Dashboard logo (your report):** was a non‑link `<div>`, and its flex `gap:10px` (meant for the icon) also fell *between* "fault" and "line" because they were separate flex items. Wrapped the word in one `<span>` (gap → 0, reads "faultline") and made the logo an `<a href="/index.html">` → clicking it returns to the marketing site. (There's also a "Marketing site ↗" item in the avatar menu.)

---

## 10. Strategy — the billionaire‑investor teardown (and what to do about it)

Three ruthless investor personas (dev‑tools, AI‑infra, brand) reviewed it. They converged. The **top moves**, ranked, that turn this from "clever tool" into "fundable company":

1. **Reposition: audit → "catch resilience REGRESSIONS in CI."** A one‑time "find your silent bugs" audit has brutal retention (run twice, uninstall). The durable product is a **per‑PR gate**: "Resilience 87→71 — new silent failure introduced in this diff," posted as a GitHub PR comment. Same engine, completely different retention curve. *(Started: hero/orbit/product copy now say "catch regressions / fail the build." Finish: the PR‑comment GitHub Action.)*
2. **Fix the oracle — switch to deterministic fault‑INVARIANTS.** Today "is the answer wrong?" rests on a stochastic LLM‑judge vs a non‑deterministic baseline = multiplicative false positives = an alarm engineers mute. Instead check **fault‑specific behavioral invariants** that need no ground truth: stale‑data → did the agent flag staleness? truncate → did it act as if the list were complete? wrong‑number → did it proceed past an impossible value? This is the #1 technical de‑risk. Build a `(fault → invariant)` library — that's real IP.
3. **Build the moat = data, not the engine.** The engine is copyable in a weekend. The defensible asset is the **"Agent Resilience Index"**: opt‑in, anonymized `(framework, tool type, fault, verdict)` from every run → "your stale‑data resilience is bottom‑quartile for support agents." Ship opt‑in telemetry from v0.1 (be loud about it — infra crowd hates sneaky telemetry).
4. **Measure rigor + publish it.** Use N‑sample baselines (measure a *rate shift*, not a single flip), test against a **real LLM agent** (not just the offline smoke test), and **publish your own false‑positive rate**. Founders who publish their error rate get believed.
5. **GTM = a weekly "we broke a famous agent" content engine**, not "Show HN and pray." Pick the **MCP wedge** ("does your agent survive a misbehaving MCP server?" — timely, painful, built‑in audience) and narrow the ICP to **action‑taking agents** (coding, financial‑ops) where a silent‑wrong has a price tag. Use the founder age for press/stage, never as the open of a buyer conversation.
6. **Proof on the site.** Add a real recorded "caught a silent failure in [famous OSS agent]" demo, GitHub stars/installs when real, and the founder‑origin line ("built on flightlog's interception engine — the hard part is already shipped"). Sell the *catch* (the failing, red dashboard), not the calm empty state. *(Don't fake stars/quotes — investors said founders who claim zero get audited and die.)*

The instinct ("inject, don't just detect") is genuinely sharp — but as of **mid‑2026 the room is filling fast** (Azure Chaos Studio extending to agent scenarios, Fastio positioning an "agent chaos engineering" platform, eval tools like DeepEval/Pydantic Evals bolting on chaos, TDS/VentureBeat writing the narrative). So the window to lead on **proof** is short. The easy 80% (the injection engine) is built — and is exactly what's commoditizing. The hard 20% (deterministic silent‑wrong detection + the data moat + the CI‑regression retention framing) is both the work ahead and the only durably defensible part. The demo that catches a real *silent* failure an eval/judge misses is now urgent, not optional.

---

## 11. Known limitations / deferred

- **3D quality** is GPU‑only (software renderers show it flat). Fallbacks exist everywhere.
- **GitHub OAuth** needs the provider enabled in Supabase (+ a GitHub OAuth app) — button auto‑hides until then.
- **Email**: dev uses confirmation‑off; production needs custom SMTP (Resend/Postmark) + branded templates for emails from your own domain.
- **Billing/Stripe**: stubbed (pricing is a placeholder) — wire when there's a paying customer.
- **Team invites**: UI present, backend "coming soon".
- **The CLI `--push` + GitHub Action ingest is now BUILT** (`faultline/report.py` + a `--push` flag that auto-fires when `FAULTLINE_TOKEN` is set + `action.yml` passthrough). Verified end-to-end against live Supabase (a fake token correctly round-trips to the `ingest_run` RPC → "invalid token"; a real token populates the dashboard). To use: mint a token in the app (Integrations/Settings), set `FAULTLINE_URL`/`FAULTLINE_KEY`/`FAULTLINE_TOKEN` (env or CI secrets), run `faultline run --push`. *(Remaining real-data step: a valid token is minted per-project in the app — only you can do that.)*
- Minor cosmetics still open: footer Privacy/Terms links pending for launch; the orbit 3D shard could take a 1‑word label; the agent‑card sparkline could add a hover tooltip. (The overview chart 30d/90d/1yr pills are now functional, not decorative.)

---

*Daily workflow: `cd site && ./start.sh`, edit, refresh. Everything reads from your own Supabase once the SQL is run. — This guide + `OVERNIGHT_RUN_LOG.md` are the source of truth.*
