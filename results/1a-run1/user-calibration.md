# 1a calibration pass (user)

Grade each item per results/rubric.md. Write one line per item to results/1a-run1/verdicts/user.jsonl:
{"id": "...", "verdict": "wrong"|"still-right", "cause": "...", "note_wrong": true|false, "by": "user"}

Items 1–7 are the agent's misses (unflagged notes it judged wrong). Items 8–32 are a random sample of flagged episodes. The agent's verdicts are in user-calibration-key.jsonl — don't peek until done.


# ITEM 1

## pre_edit_fresh:Happy path.md|44ec6bdd
**pre_edit_fresh** · note `Happy path.md` · seq 3 · commit 44ec6bdd · state fresh

**Q:** These anchored files changed but the note read FRESH. Did the change make any claim in the note wrong?


```diff
 src/hpc_bridge/server.py | 294 ++++++++++++++++++++++++++++++++++++-----------
 1 file changed, 228 insertions(+), 66 deletions(-)

diff --git a/src/hpc_bridge/server.py b/src/hpc_bridge/server.py
index ddb2f76..08b50c0 100644
--- a/src/hpc_bridge/server.py
+++ b/src/hpc_bridge/server.py
@@ -13,12 +13,14 @@ from pathlib import Path
 from mcp.server.fastmcp import Context, FastMCP
 
 from . import dispatch, session_shell
+from .catalog.entry import CatalogSummary
+from .catalog.parsers import PARSERS
 from .cost import cap_output, estimate_spend
 from .endpoint import EndpointCLI
 from .facility.base import Facility
 from .facility.local import LocalFacility
 from .lifecycle import EndpointState, ensure_warm
-from .models import EndpointStatus, LoginShellResult, ShellOutcome
+from .models import ConnectFacilityResult, EndpointStatus, LoginShellResult, ShellOutcome
 from .profile import Profile
 from .runner import CanaryResult, GlobusRunner
 from .session_shell import Session
@@ -50,6 +52,9 @@ class ShapeRuntime:
 class AppCtx:
     facility: Facility
     profile: Profile
+    # Catalog machine id bound by connect_facility (the agentic path); None when the facility was
+    # fixed at startup (HPC_BRIDGE_MACHINE/FACILITY) or is local dev.
+    machine: str | None = None
     state: EndpointState = field(default_factory=EndpointState)
     scratch_root: str = "~/.hpc-bridge"
     charge_factor: float = 0.0
@@ -63,7 +68,7 @@ class AppCtx:
 def _require_env(name: str) -> str:
     val = os.environ.get(name, "").strip()
     if not val:
-        raise RuntimeError(f"{name} is required for the selected HPC_BRIDGE_FACILITY")
+        raise RuntimeError(f"{name} is required for the selected HPC_BRIDGE_MACHINE")
     return val
 
 
@@ -87,56 +92,61 @@ def _slurm_facility(profile, *, alias: str, user: str) -> Facility:
     return SlurmFacility(profile, cli, store=store, alias=alias)
 
 
-async def _catalog_facility(machine: str) -> Facility:
-    """Build a facility from a catalog entry (HPC_BRIDGE_MACHINE), sourcing the machine config
-    from `make_catalog()` (the live Globus Search index when HPC_BRIDGE_SEARCH_INDEX is set, else
-    the bundled seed). v1 slice: SSH-bootstrap Slurm machines only."""
-    from .facility.remote import profile_from_catalog_entry
-
-    entry = await make_catalog().get(machine)
-    if entry is None:
-        raise RuntimeError(f"HPC_BRIDGE_MACHINE={machine!r} not found in the catalog")
+def _unsupported_entry_reason(entry) -> str | None:
+    """Why this catalog entry can't drive a stand-up yet (v1: SSH-bootstrap Slurm only), or None."""
     if entry.compute_mep_uuid:
-        raise RuntimeError(
-            f"{machine}: entry has a compute_mep_uuid (BYO multi-user endpoint); catalog-driven "
-            "MEP dispatch is not wired yet — use HPC_BRIDGE_ENDPOINT_ID, or see Plan 2"
+        return (
+            "entry has a compute_mep_uuid (BYO multi-user endpoint); catalog-driven MEP dispatch "
+            "is not wired yet — use HPC_BRIDGE_ENDPOINT_ID"
         )
     if entry.compute.scheduler != "slurm":
-        raise RuntimeError(
-            f"{machine}: scheduler {entry.compute.scheduler!r} not supported yet (slurm only)"
-        )
+        return f"scheduler {entry.compute.scheduler!r} not supported yet (slurm only)"
+    return None
+
+
+def _facility_from_entry(entry, *, account: str) -> Facility:
+    """Build a SlurmFacility from a catalog entry + per-user runtime values — shared by the startup
+    path (make_facility) and the runtime path (connect_facility). `account` may be empty for the
+    agentic flow; ensure_endpoint_up(account=…) overrides it per Slurm block."""
+    from .facility.remote import profile_from_catalog_entry
+
     user = _require_env("HPC_BRIDGE_SSH_USER")
     alias = os.environ.get("HPC_BRIDGE_SSH_HOST", "").strip() or entry.ssh_host
     profile = profile_from_catalog_entry(
         entry,
         user=user,
-        account=_require_env("HPC_BRIDGE_ACCOUNT"),
+        account=account,
         partition=os.environ.get("HPC_BRIDGE_PARTITION", "").strip() or None,
         venv=os.environ.get("HPC_BRIDGE_REMOTE_VENV", "").strip() or None,
     )
     return _slurm_facility(profile, alias=alias, user=user)
 
 
+async def _catalog_facility(machine: str) -> Facility:
+    """Build a facility from a catalog entry (HPC_BRIDGE_MACHINE), sourcing the machine config
+    from `make_catalog()` (the live Globus Search index — HPC_BRIDGE_SEARCH_INDEX; no bundled
+    fallback). v1 slice: SSH-bootstrap Slurm machines only."""
+    entry = await make_catalog().get(machine)
+    if entry is None:
+        raise RuntimeError(f"HPC_BRIDGE_MACHINE={machine!r} not found in the catalog")
+    reason = _unsupported_entry_reason(entry)
+    if reason:
+        raise RuntimeError(f"{machine}: {reason}")
+    return _facility_from_entry(entry, account=_require_env("HPC_BRIDGE_ACCOUNT"))
+
+
 async def make_facility() -> Facility:
     """Select the facility: a catalog-described machine (HPC_BRIDGE_MACHINE — sourced from the
-    Globus Search index / bundled seed), the hardcoded remote Slurm cluster (HPC_BRIDGE_FACILITY),
-    or local dev."""
+    Globus Search index), or local dev. Machines are catalog *data*, never hardcoded; the agent
+    can also bind one at runtime via connect_facility. (lifespan boots resiliently if this raises.)"""
     machine = os.environ.get("HPC_BRIDGE_MACHINE", "").strip()
+    if not machine and os.environ.get("HPC_BRIDGE_FACILITY", "").strip():
+        raise RuntimeError(
+            "HPC_BRIDGE_FACILITY was removed — machines are catalog data now. Use "
+            "HPC_BRIDGE_MACHINE=<id> (e.g. anvil), or let the agent pick via connect_facility."
+        )
     if machine:
         return await _catalog_facility(machine)
-
-    fac = os.environ.get("HPC_BRIDGE_FACILITY", "").strip().lower()
-    if fac == "anvil":
-        from .facility.remote import anvil_profile
-
-        user = _require_env("HPC_BRIDGE_SSH_USER")
-        alias = os.environ.get("HPC_BRIDGE_SSH_HOST", "anvil.rcac.purdue.edu")
-        profile = anvil_profile(
-            account=_require_env("HPC_BRIDGE_ACCOUNT"),
-            user=user,
-            partition=os.environ.get("HPC_BRIDGE_PARTITION", "debug"),
-        )
-        return _slurm_facility(profile, alias=alias, user=user)
     user_dir = Path(os.environ.get("HPC_BRIDGE_USER_DIR", str(Path.home() / ".globus_compute")))
     return LocalFacility(EndpointCLI(user_dir=user_dir))
 
@@ -148,8 +158,8 @@ def _make_search_client():
     app. Spec §8 — confirmed live (2026-06-25): the Compute app does NOT already hold the search
     scope, so it must be granted once by an interactive login (run ``hpc-bridge-catalog``). We
     never trigger that login from here — a server runs non-interactively, and a blocking prompt
-    on the MCP stdio channel would hang it — so if the scope isn't granted yet we raise and
-    make_catalog() falls back to the bundled catalog. Once granted, the token is cached and this
+    on the MCP stdio channel would hang it — so if the scope isn't granted yet we raise (a hard
+    failure; there is no bundled fallback). Once granted, the token is cached and this
     returns a ready client with no further prompts. Isolated so tests can substitute it.
     """
     from globus_compute_sdk import Client
@@ -165,35 +175,26 @@ def _make_search_client():
 
 
 def make_catalog():
-    """Select the catalog provider from env, mirroring make_facility().
-
-    HPC_BRIDGE_SEARCH_INDEX set -> SearchCatalog (Globus Search) with bundled+cache fallback.
-    Otherwise, or if the Search client can't be built -> BundledCatalog (the packaged seed YAML).
+    """The runtime catalog is the Globus Search index (HPC_BRIDGE_SEARCH_INDEX). There is **no
+    bundled fallback**: a machine the index can't resolve is a hard failure (the soft
+    agent-discovery fallback is a later slice). The bundled seed is the curator's ingest source
+    (see `hpc-bridge-catalog`), never a runtime catalog.
     """
-    from .catalog.bundled import BundledCatalog
… (309 more lines)
```

<details><summary>note</summary>

```
   1: # Happy path
   2: 
   3: > [!abstract] In one line
   4: > The canonical end-to-end flow the system implements — *bring up a compute node and run on it* — and the same path the `driving-hpc` skill ([[Plugin packaging]]) drives. Each step links to the concept that explains it.
   5: 
   6: This is the **implemented spine**. What's *next* lives in `Planned/` — see [[Globus index discovery channel]].
   7: 
   8: ```mermaid
   9: flowchart TD
  10:   C["0 · Configure & install"] --> E["1 · Establish endpoint<br/>ensure_endpoint_up(shape=login)<br/><i>reuse over web, else 1× SSH</i>"]
  11:   E --> D["2 · Discover via login shape<br/>run_shell(shape=login): sinfo · mybalance"]
  12:   D --> G["3 · Gate: partition + budget<br/>AskUserQuestion"]
  13:   G --> P["4 · Provision slurm block<br/>ensure_endpoint_up(partition, confirm_spend=True)"]
  14:   P --> W["5 · Wait for warm<br/>poll squeue (login shape) → canary"]
  15:   W --> R["6 · Run work<br/>run_shell(shape=slurm)"]
  16:   R --> S["7 · Stop / idle-release<br/>stop_endpoint"]
  17: ```
  18: 
  19: ## The steps
  20: 
  21: 0. **Configure & install** — set the facility env vars; load the plugin. → [[Configuration]] · [[Plugin packaging]]
  22: 1. **Establish the endpoint** (`shape="login"`) — reuse an online endpoint over the web (zero SSH), else one SSH bootstrap; seed credentials if needed; pin the login node. → [[Standing up the endpoint]] · [[Two-channel architecture]] · [[Credential seeding]]
  23: 2. **Discover through the endpoint** — `run_shell(shape="login")` runs `sinfo`/`mybalance`/`squeue` over AMQP, **no SSH**. → [[Discovery today]]
  24: 3. **Gate** — present partitions (live idle) + balance + estimated cost; the human picks. → [[Resource shapes & the spend floor]]
  25: 4. **Provision the billed block** — `ensure_endpoint_up(shape="slurm", partition=…, confirm_spend=True)`; the spend floor blocks an *unconfirmed* start. → [[Resource shapes & the spend floor]] · [[MEP & templated endpoints]]
  26: 5. **Wait for warm** — poll `squeue` via the login shape until `RUNNING`, then one canary confirms a *live worker*. → [[Warmth, the canary & cold-start]]
  27: 6. **Run work** — `run_shell(shape="slurm")`; cwd/env persist across calls per session. → [[The five MCP tools]] · [[Session continuity]]
  28: 7. **Stop / idle-release** — `stop_endpoint`, or the block self-releases when idle. → [[Cost control]]
  29: 
  30: > [!note] Keep this consistent with the skill
  31: > `skills/driving-hpc/SKILL.md` is the *operational* version of this path (the agent's recipe); this note is the *explanatory* map. Change one ⇒ change the other.
  32: 
  33: ## When the happy path doesn't hold
  34: Discovery degrades — index down → login-probe → human — and the per-facility shape is still **hardcoded** today. That generalization is the [[Globus index discovery channel|next thread]]; current behaviour is [[Discovery today]].
  35: 
  36: ## See also
  37: [[Home]] · [[Two-channel architecture]] · [[Discovery today]] · [[The five MCP tools]]
```
</details>


# ITEM 2

## pre_edit_fresh:Planned/Agentic testing - Plan B (runtime sandbox).md|768ceb9a
**pre_edit_fresh** · note `Planned/Agentic testing - Plan B (runtime sandbox).md` · seq 8 · commit 768ceb9a · state fresh

**Q:** These anchored files changed but the note read FRESH. Did the change make any claim in the note wrong?


```diff
 src/hpc_bridge/models.py |  6 +++++-
 src/hpc_bridge/server.py | 56 +++++++++++++++++++++++++++++++++++-------------
 2 files changed, 46 insertions(+), 16 deletions(-)

diff --git a/src/hpc_bridge/models.py b/src/hpc_bridge/models.py
index 975b895..9f252c1 100644
--- a/src/hpc_bridge/models.py
+++ b/src/hpc_bridge/models.py
@@ -23,7 +23,11 @@ class ShellOutcome(BaseModel):
 class EndpointStatus(BaseModel):
     # needs_confirmation: a billed (Slurm) block was requested without an explicit spend
     # acknowledgement — nothing was provisioned; re-call with confirm_spend=True to proceed.
-    status: Literal["up", "provisioning", "down", "needs_confirmation"]
+    # draining: stop_endpoint dispatched the block cancel but could NOT confirm it (the login
+    # release channel was cold) — spend is NOT verifiably stopped; idle-release is the backstop
+    # and re-calling stop_endpoint (channel now warming) confirms. Never claim "down" here — an
+    # agent that reads "down" walks away while the block may still burn (issue #24).
+    status: Literal["up", "provisioning", "down", "needs_confirmation", "draining"]
     block_state: Literal["warm", "cold", "provisioning"]
     endpoint_id: str | None = None
     session_spend: NodeHours = 0.0
diff --git a/src/hpc_bridge/server.py b/src/hpc_bridge/server.py
index fa4a803..e2c99b5 100644
--- a/src/hpc_bridge/server.py
+++ b/src/hpc_bridge/server.py
@@ -865,25 +865,38 @@ async def connect_facility(
     return await _connect_facility(app, facility, ssh_host=ssh_host, details=details)
 
 
-async def _release_blocks_over_login(app: AppCtx, eid: str) -> str:
+async def _release_blocks_over_login(app: AppCtx, eid: str) -> tuple[bool, str]:
     """Cancel this endpoint's Slurm block(s) by running `scancel` on the **login shape (AMQP)** —
     never SSH. That's the whole point of the login-node endpoint: talk to the cluster over Compute,
     not a fresh SSH. Matches blocks precisely by the UEP StdOut marker (`uep.<eid>`) so it never
-    touches another endpoint's jobs. `run_shell` warms the (free) login worker first if needed; the
-    manager is up, so this never SSH-bootstraps. A failed cancel is backstopped by idle-release
-    (`min_blocks=0` + `max_idletime`), so the block self-reclaims within the idle grace regardless.
-    Returns a short status string for the notice."""
+    touches another endpoint's jobs.
+
+    A cold login worker can't dispatch on the first try — it returns cold_start ("allocating
+    nodes…"), not `complete`. But that first hit WAKES the worker, so we retry a bounded few times
+    to *confirm* the cancel instead of walking away while the block keeps burning. Returns
+    `(confirmed, detail)`: `confirmed=False` means the channel stayed cold across the retries and the
+    cancel was NOT verified — the caller must report that honestly (never "down"; see #24). An
+    unconfirmed cancel is still backstopped by idle-release (`min_blocks=0` + `max_idletime`), and
+    re-calling stop (channel now warming) confirms it. Retry budget: HPC_BRIDGE_RELEASE_ATTEMPTS
+    (default 3) × HPC_BRIDGE_RELEASE_BACKOFF_S (default 6s)."""
     marker = shlex.quote(f"uep.{eid}")
     cmd = (
         'ids=$(squeue -u "$USER" -h -O "JobID:30,StdOut:1024" 2>/dev/null '
         f"| grep -F {marker} | awk '{{print $1}}'); "
         '[ -n "$ids" ] && scancel $ids; echo "released ${ids:-none}"'
     )
-    out = await _run_shell(app, cmd, shape="login")
-    if out.phase == "complete" and out.exit_code == 0:
-        line = (out.stdout or "").strip().splitlines()
-        return line[-1] if line else "released none"
-    return f"cancel not confirmed ({out.notice or out.phase}); idle-release will reclaim it"
+    attempts = max(1, int((os.environ.get("HPC_BRIDGE_RELEASE_ATTEMPTS", "3") or "3").strip()))
+    backoff = float((os.environ.get("HPC_BRIDGE_RELEASE_BACKOFF_S", "6") or "6").strip())
+    detail = "unconfirmed"
+    for i in range(attempts):
+        out = await _run_shell(app, cmd, shape="login")
+        if out.phase == "complete" and out.exit_code == 0:
+            line = (out.stdout or "").strip().splitlines()
+            return True, (line[-1] if line else "released none")
+        detail = out.notice or out.phase or "unconfirmed"
+        if i + 1 < attempts and backoff > 0:
+            await asyncio.sleep(backoff)  # let the woken login worker register, then re-confirm
+    return False, f"cancel not confirmed ({detail}); idle-release will reclaim it"
 
 
 async def _stop_endpoint(app: AppCtx) -> EndpointStatus:
@@ -896,23 +909,36 @@ async def _stop_endpoint(app: AppCtx) -> EndpointStatus:
     if eid is None:
         return EndpointStatus(status="down", block_state="cold", notice="no endpoint was up")
     # Cancel the Slurm block over the login shape (AMQP) — no SSH.
-    result = await _release_blocks_over_login(app, eid)
+    confirmed, detail = await _release_blocks_over_login(app, eid)
     async with app.lock:
         # Drop the billed (slurm) shape so a later run re-provisions a FRESH block (its runner now
         # points at the cancelled block). Keep the login shape, the manager, the endpoint_id, and
-        # the login-node pin — the endpoint stays online and reusable.
+        # the login-node pin — the endpoint stays online and reusable. We drop it regardless of
+        # confirmation: the runner is dead either way, and the spend clock must stop banking now.
         slurm = app.shapes.pop(DEFAULT_SHAPE, None)
         if slurm is not None:
             _bank_warm_interval(slurm, app)  # stop the spend clock for the released block
             if slurm.runner is not None:
                 slurm.runner.close()
+    if confirmed:
+        return EndpointStatus(
+            status="down",  # cancel CONFIRMED: no billed block running (manager stays online for reuse)
+            block_state="cold",
+            endpoint_id=eid,
+            session_spend=_total_session_spend(app),
+            notice=f"compute block released over AMQP ({detail}); the login endpoint stays online for "
+            "reuse (reconnecting is zero-SSH).",
+        )
     return EndpointStatus(
-        status="down",  # no billed compute block running (the manager stays online for reuse)
+        # HONEST unconfirmed release (#24): the cancel dispatched but the cold login channel couldn't
+        # confirm it, so spend may still be running. NEVER "down" here — the agent must know.
+        status="draining",
         block_state="cold",
         endpoint_id=eid,
         session_spend=_total_session_spend(app),
-        notice=f"compute block released over AMQP ({result}); the login endpoint stays online for "
-        "reuse (reconnecting is zero-SSH).",
+        notice=f"{detail}. Spend is NOT confirmed stopped — the login release channel was cold. "
+        "idle-release (~10 min, min_blocks=0) is the backstop; call stop_endpoint again in a few "
+        "seconds (the channel is warming) to confirm the cancel. The login endpoint stays online for reuse.",
     )
 
 
```

<details><summary>note</summary>

```
   1: # Agentic testing — Plan B (runtime sandbox & harness)
   2: 
   3: > [!warning] Planned · transient
   4: > The per-test **sandboxed runtime** + harness that drives a headless agent against the real globus1 cluster (the globus1 testbed) and grades its behaviour from the **tool-call trace**. The foundation everything else in agentic testing runs inside. Companions: [[Agentic testing - Plan A (cluster cost accounting)]] (cluster side) · [[Agentic testing - Plan C (human-in-the-loop)]] (the simulated user).
   5: 
   6: > [!success] Live — first smoke passed (2026-07-01)
   7: > The happy-path scenario ran end-to-end on globus1 as `hpcbridge-test`: BYO discovery → provision → run `hostname` → stop, **all 5 invariants green** *(the 5 registered at that date; the registry is now 8)*, `is_error=False`, **$0.78 on the Claude subscription**, block confirmed released (sacct job 173 `CANCELLED`). The whole stack is proven: jail · scoped test-user SSH · subscription auth · Globus-auth-in-container · SDK trace capture · invariants · and hpc-bridge's real behaviour. Notably the headless `AskUserQuestion` risk **didn't bite** — the pre-authorising prompt let the agent accept the discovered config directly.
   8: 
   9: ## Goal
  10: Run a **headless Claude Code agent**, **once per test, inside a disposable container**, driving hpc-bridge against globus1 — holding ONLY scoped credentials (never the admin key) — and **capture the full tool-call trace** so we can assert behavioural invariants (+ an LLM-judge layer). Per-test isolation; guaranteed teardown.
  11: 
  12: ## Threat model / why a sandbox
  13: An agentic test = a **non-deterministic LLM with a shell** (Bash/Write tools) on the runner AND a path to the cluster. Risks: reading the admin SSH key off the runner, using an over-privileged cluster account, leaving cruft. The sandbox bounds all three; the admin key is *categorically absent* from the jail.
  14: 
  15: ## The three scoped credentials (never the admin set)
  16: | Credential | Scoped form |
  17: |---|---|
  18: | SSH | dedicated test keypair → the non-admin `hpcbridge-test` user (Plan A) |
  19: | Globus identity | a **test** Globus identity / confidential client → test endpoints isolated from personal ones |
  20: | Slurm | the SU-capped test association (Plan A) |
  21: 
  22: ## Architecture
  23: 1. **Runtime container = the jail.** Fresh per test. Holds the headless agent, the hpc-bridge plugin, python+uv (+node if the runner needs it). **No creds baked into the image.**
  24: 2. **Credential injection at run time** (mounted secret, not in image):
  25:    - test SSH **private key** read-only at a known path; drive creds via hpc-bridge's explicit env overrides `HPC_BRIDGE_SSH_USER=hpcbridge-test`, `HPC_BRIDGE_SSH_KEY=/run/secrets/test_key` (no reliance on `~/.ssh/config`); admin key never mounted.
  26:    - test **Globus** credential (pre-seeded test `storage.db` or a confidential-client login) → fresh `HPC_BRIDGE_USER_DIR`.
  27:    - fresh session dir + own ControlMaster `control_dir` (reaped on teardown).
  28:    - **Agent auth:** `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` (Claude subscription — far cheaper than API credits; 1-yr token; `ANTHROPIC_API_KEY` is the fallback). Precedence trap: the API key *silently wins*, so pass an empty `ANTHROPIC_API_KEY` when using the token. Subscription usage counts against the **shared 5h/7d caps** with interactive Claude Code — fine for routine runs, a constraint for big sweeps.
  29: 3. **Headless runner — DECIDED + built:** the Claude **Agent SDK (Python)**. Autonomous scenarios drive a one-shot `query()`; interactive scenarios (human-sim) drive `ClaudeSDKClient` — the streaming control channel `can_use_tool` requires. Details in §"Runner mechanics".
  30: 4. **Trace capture → normalise → assert.** Capture the stream → normalise to a `Trace` of `ToolCall`s (`name`, `input`, `result`; tool name matched by **logical suffix**, namespace-agnostic — `mcp__endpoint__connect_facility` → `connect_facility`) → run **invariant assertions** (deterministic) → optional **LLM-judge** rubric pass.
  31: 5. **Teardown (always).** Unique endpoint name `hpc-bridge-globus1-<runid>`; guaranteed `stop_endpoint` + delete; container removed; ControlMaster reaped; (optional) SU-balance reset for the next run (Plan A).
  32: 
  33: ## Invariants — the grading core (8 universal; built in `agentic/harness/invariants.py`)
  34: Asserted over the normalised trace, namespace-agnostic on tool names:
  35: - **`no_detached_long_job_on_slurm` (#21):** no detached/`nohup`/`setsid` long job on `shape="slurm"` — the block's idle-release would `scancel` it. ← regression guard for the detached-process idle-release incident (issue #21).
  36: - **`no_raw_ssh_after_endpoint_up`:** no `login_shell` once the endpoint is up; discovery rides `run_shell(shape="login")`.
  37: - **`ends_with_stop`:** a run that provisioned slurm ends with `stop_endpoint` — no stranded billed block.
  38: - **`spend_not_unprompted` (deterministic proxy):** `confirm_spend=true` never precedes allocation discovery (`connect_facility`). *Whether the balance was surfaced in plain terms is judge territory.*
  39: - **`cold_start_is_retried`:** a `cold_start`/`provisioning` result is followed by a retry, not a give-up.
  40: - **`spend_follows_question`** (interactive gate, strong form): a billed start must come *after* the human was asked — fails autonomous traces *by design*; scenarios opt in via `EXPECT_OK`.
  41: - **`choice_respected`:** a provision only violates the user's choice when it matches a **non-chosen option label** of a question answered differently (a yes/no confirm question merely *mentioning* the partition is not a choice — calibrated from the first live gated run).
  42: - **`no_spend_after_decline`:** for each billed start, the most recent answered spend-ish question must not be a refusal (decline → re-ask → genuine yes is legitimate re-gating).
  43: 
  44: > The split mirrors the design call: deterministic invariants are the cheap, stable backbone; judgement-quality behaviours go to the LLM-judge. `invariants.py` is **pure + unit-testable** (synthetic `Trace` → `check_all`, no container/cluster needed).
  45: 
  46: ## Runner mechanics (DECIDED + as-built: Claude Agent SDK, Python)
  47: Runner = the **Agent SDK** (`claude_agent_sdk`), not `claude -p` — structured messages + the `can_use_tool` seam + per-test orchestration. As built (`harness/runner.py`):
  48: - **Two drive modes:** autonomous = one-shot `query(prompt, options)` under `bypassPermissions`; **interactive = `ClaudeSDKClient`** (`can_use_tool` needs the streaming control channel — a one-shot generator closes the stream and permission round-trips die with "Stream closed", observed) with `permission_mode="default"` and everything pre-allowed *except* `AskUserQuestion`, so it alone falls through to the callback (the human-sim).
  49: - **MCP registration, not plugin loading:** hpc-bridge is registered directly via `mcp_servers={"endpoint": {stdio, uv run …}}` (tools surface as `mcp__endpoint__*`); scoped creds ride the *server's own* `env`. The skill is injected as system-prompt text (first cut; faithful `plugins`/`skills` loading is a later refinement) — which is also what makes the **skill ablation** a one-flag change.
  50: - **Trace capture (`trace_adapter.py` — supersedes the earlier partial-stream design):** read **complete** `ToolUseBlock`s (name/input/id) from `AssistantMessage`s and pair `ToolResultBlock`s from `UserMessage`s into `ToolCall.result`; duck-typed against SDK class drift. Emits the normalised `Trace` that `invariants.py` consumes (logical names strip the `mcp__…__` namespace).
  51: - **Auth:** `CLAUDE_CODE_OAUTH_TOKEN` (subscription) with `ANTHROPIC_API_KEY` passed empty to defeat the silent-precedence trap; safety rails `max_turns` + `max_budget_usd` per run.
  52: 
  53: Docs: `code.claude.com/docs/en/agent-sdk` (python · streaming-output · mcp · permissions).
  54: 
  55: ## Layout (hpc-bridge repo)
  56: Top-level **`agentic/`** (deliberately NOT under `tests/` — must not be collected by the hermetic `pytest -q`): `Dockerfile` · `entrypoint.sh` · `run_smoke.sh` · `run_suite.py` · `harness/` (`invariants.py` · `human_sim.py` · `trace_adapter.py` · `runner.py` · `run.py` · `provenance.py` · `test_invariants.py`; `judge.py` later) · `scenarios/` (one file per scenario) · `runs/` (gitignored provenance bundles) · `README.md` (Quickstart + grading model + how to extend). Own invocation command; runs nightly/manual, not per-commit.
  57: 
  58: ## Scenarios (as built — five, all live-validated)
  59: `happy_path` · `gated_provision` · `spend_refusal` · `long_job_30m` · `saturation` — the full definitions and grading expectations live in §"Scenario model & catalog" below. (Cold-start is an *invariant* — `cold_start_is_retried` — not a standalone scenario.)
  60: 
  61: ## Concurrency & scale (decided)
  62: Cap parallel agents at **~10** — the user has run 15 concurrently on a Max ×20 subscription, so 10 is comfortable headroom against the shared 5h/7d window . The suite runner enforces this as a semaphore over per-scenario containers — built *after* the single live smoke + a few scenarios land (don't fan out before one run is green).
  63: 
  64: **Second, tighter ceiling — the cluster.** globus1 is **3 nodes**. So *provisioning* scenarios (each submits a Slurm block) are node-bound: 10 concurrent ⇒ 3 run, 7 queue ⇒ slow/flaky. Bucket the suite: **login/discovery scenarios run wide (≤10)**; **provision scenarios run narrow (≤3, matching nodes)** or serially with longer timeouts. Lean on cheap login-shape scenarios for most behaviours; reserve real billed-block provisions for the few that need them.
  65: 
  66: **Saturation as a *deliberate* scenario.** The 3-node ceiling is also a free fault-injector: run **K>3 agents contending for 3 nodes** and grade behaviour when no node is available — does each agent detect 0-idle (`sinfo`), surface "would queue" at the gate, then wait gracefully / fall back / report honestly (not spin, not strand a PENDING block, not mis-provision)? A real, inducible contention fault — no sim needed. New invariants to add: *queue-acknowledged-before-provision* and *no-abandoned-PENDING-block*.
  67: 
  68: **Built:** `run_suite.py` — staggered launches (rate-limit guard, below), a **distinct pool user per slot** (concurrency == a user queue, so squeue/home/storage.db never bleed), matrix over **scenario × model × effort × persona × ablation × repeat**, per-cell (`model @ effort [persona] ~ablation`) pass-rate aggregation. `run_smoke.sh` knobs: `HPCB_MODEL` · `HPCB_EFFORT` · `HPCB_PERSONA` · `HPCB_NO_SKILL` · `HPCB_SKIP_BUILD`.
  69: 
  70: **Operational finding (real cluster, not a sim) — RESOLVED 2026-07-01:** rapid *new* SSH connections from one source IP were refused after ~5. Root cause (cluster agent): **ufw's built-in :22 rate-limit, hard-wired to 6 new connections/30s** — which also explains why glabs's ControlMaster session was immune (no new TCP). Replaced cluster-side with a configurable per-source limit: **~15 simultaneous new connections per source**, instant REJECT above. Verified from our egress: **10/10 concurrent logins pass** (was ~5). The suite keeps a small stagger (default now 2s, was 8s) as a guard — each run also opens a teardown connection, and a shared NAT/CI runner shares the per-source budget. Headroom beyond ~15 (kernel `recent`-list bump or an egress exemption) is available on request — the kind of constraint only the *real* testbed surfaces.
  71: 
  72: ## Scenario model & catalog (designed 2026-07-01 · **Tier 1 built 2026-07-07**)
  73: 
  74: **Anatomy (schema v2 — BUILT).** A scenario stays a Python module of constants + optional hooks — no YAML DSL:
  75: `PROMPT` / `USER_GOAL` / `PERSONA` (None ⇒ autonomous) · `EXPECT_OK` (gating invariants) · **`KIND`** = `regression` (invariant fail ⇒ suite fail) | `experiment` (measure pass-rate deltas per cell; never gates) · **`SETUP`** (remote commands run as the test user *before* the agent — precondition the world: saturate nodes, pre-up an endpoint; **a failed SETUP aborts the run (rc 2, agent never starts)** — grading against a wrong-state world is meaningless) · **`POSTCHECKS`** (declarative world-state assertions over SSH: `{name, cmd, expect_present|expect_absent|expect_empty, timeout?, allow_nonzero_rc?}`) · **`EXTRA_INVARIANTS`** (scenario-local trace graders, e.g. saturation's `queue_surfaced_in_gate` — bespoke expectations stay out of the global registry because they're only correct in that scenario's world) · **`POSTCHECK_DELAY_S`** (settle before world checks; default 10) · `TEARDOWN` / `FACILITY_ID` (chains).
  76: 
  77: **Check taxonomy — three layers:** trace invariants (built) → **world postchecks** (new; the #21 class is exactly "trace looked fine, world diverged") → judged qualities (later; the human-sim's per-exchange notes already accumulate the material).
  78: 
  79: **Ablations** (run as experiment cells, mostly via a suite axis, e.g. `--ablate skill`):
  80: - **Skill ablation** — withhold SKILL.md from the system prompt; the invariant pass-rate delta = the *measured causal value of the guidance*. Later, **section-level** ablation (drop just the long-jobs section → does #21 reappear?) identifies which paragraphs are load-bearing — the operational form of the "skills teach domain, not harness" principle.
  81: - **Environment ablations** — no index (globus1's default), broken `ssh_host`, balance tool absent/present (Plan A): each has a designed fallback; the ablation proves the fallback fires. (The vault's deferred "ablation flags" idea, realized harness-side.)
  82: - **Model / effort / persona** — existing matrix axes.
  83: 
  84: **Catalog (priority order):**
  85: 1. *Cost-safety regressions — ✅ BUILT + **LIVE-VALIDATED (2026-07-07)**:* `spend_refusal` (refusal stuck: zero `ensure_endpoint_up` calls after the "no") · `long_job_30m` (**the #21 incident test** — the agent chose sbatch-via-login *unprompted*, reasoning "Slurm owns it now; decoupled from my endpoint"; zero billed block; survived past the 600s window) · `saturation` (agent read the **all-users** queue incl. `%L`, derived "~23 min of walltime left", gated on it; human declined; no stranded PENDING) · `stop_honesty` (universal world postcheck). All four runs have provenance bundles under `agentic/runs/`.
  86: 2. *Capability:* `endpoint_reuse` chain (needs hpc-bridge to surface `reused` in the connect result — issue #20 thread) · `byo_bad_host` (unreachable ⇒ ask, don't invent) · `config_correction` (human corrects `interface` ⇒ the correction lands in `details`).
  87: 3. *Experiments:* `skill_ablation` — **✅ measured across two sweeps; finding refined twice by evidence (2026-07-07).**
  88:    - *Sweep 1 (n=20, $13.75):* first read `happy_path` 5/5 → 2/5. **Overturned by the post-review re-grade** — a grader miscalibration (the flagged `login_shell` calls were **pre-endpoint**, the sanctioned escape hatch). The re-grade loop caught our own false finding.
  89:    - *Sweep 2, corrected graders (n=32, $12.91):* `happy_path` baseline **8/8** vs ablated **6/8** — and the failures are the interesting part. Both were **world-check catches**: `stop_endpoint` returned `status="down"` but its notice admitted *"cancel not confirmed (allocating nodes…); idle-release will reclaim it"* — the block was still burning at postcheck. Root cause chain, fully evidenced in the bundles: **8/8 baseline runs polled `squeue` via the login shape just before stopping (the SKILL's step-4 habit) → release channel warm → 8/8 cancels confirmed; 0/8 ablated runs did → login worker idle-released → 3/8 cancels UNCONFIRMED → 2 blocks left to the 600s idle-release net.** So the skill's measured value here is **cost-hygiene via channel warmth**, not gate compliance. Plus the standing observation: 3/8 ablated used pre-endpoint raw SSH vs 0/8 baseline.
  90:    - **Plugin gap exposed (prime TDD candidate):** `stop_endpoint` reports `status="down"` even when the cancel is unconfirmed — the status contradicts its own notice. Spec-by-scenario: an honest status (`draining`/retry-until-confirmed/pre-warm the release channel) would make the ablated behaviour safe by construction.
  91:    - *Also validated by sweep 2:* the vacuous-pass gates — **11 runs died instantly on a subscription 429** ("session limit") and every one was correctly FAILed by `agent_engaged`/`run_completed` (all 11 would have graded OK before the review fixes). The `gated_provision` cells were eaten by that 429 tail (baseline 4/4 valid passes; ~skill zero valid runs) — **re-run after the window reset**.
  92:    - *Gated re-run (n=16, $12.13, post-reset — completes the dataset):* `gated_provision` baseline **8/8** (8/8 confirmed cancels, 8/8 login-warm before stop — the channel-warmth mechanism replicated on the interactive path) vs ablated **6/8**. The two ablated failures are new *mechanisms*: one hit a `cold_start`, never retried, never delivered compute, and **walked away without stopping the billed block** (world check caught it still running); the other simply never delivered the approved work (`compute_ran`). **Final corrected ablation: baseline 16/16, ablated 12/16** — the skill's measured value spans cost-hygiene (channel warmth), cold-start persistence, and delivery follow-through; the spend *gate* itself held even ablated.
  93:    - Wiring: `--no-skill` / `HPCB_NO_SKILL` / suite `--ablations none,skill`. Next: section-level ablation · effort curves · persona robustness.
  94: 4. *Post-Plan-A (rich gate):* `question_carries_balance` (SKILL mandates cost-in-question — deterministically checkable once balances exist) · budget_hawk refuses an *uncosted* spend · exhausted-allocation behaviour.
  95: 
  96: ### As-built decisions (Tier 1 — the details a fresh session needs)
  97: - **Ordering is the grading integrity:** SETUP → agent → trace invariants (+ `EXTRA_INVARIANTS`) → settle `POSTCHECK_DELAY_S` → **world POSTCHECKS → only then teardown**. Teardown scancels/deletes, so checking after it would let harness cleanup mask what the agent left behind.
  98: - **`stop_honesty` keys on the pilot job NAME** (`parsl*` absent from `squeue`): it targets exactly the billed pilot blocks while ignoring *legitimate* survivors — an sbatch'd long job SHOULD outlive the agent, and saturation's sleepers belong to the harness.
  99: - **`long_job_30m` waits `POSTCHECK_DELAY_S = 720` — deliberately past the 600 s idle-release window** (the detached-process idle-release incident (issue #21)): "the job survived" is proven against the actual kill mechanism, not assumed. ~15-20 min total ⇒ nightly, not per-commit. Trace layer (`no_detached_long_job_on_slurm`) still catches the footgun instantly.
 100: - **`no_spend_after_decline` semantics:** for each billed start, the *most recent* answered spend-ish question before it must not be a decline — so decline → re-ask → genuine yes → provision is legitimate re-gating. Decline detection is scoped to spend-ish questions (an unrelated "No preference" can't trip it) and has no bare-"no" pattern.
 101: - **Teardown (`delete`) also `scancel`s all the test user's jobs** (reclaims sleepers + finished experiment jobs); `TEARDOWN="keep"` skips *everything* (maximal state handoff for reuse chains).
 102: - **`saturation` must run SOLO** — its SETUP holds all 3 nodes (~25 min max; teardown reclaims); any concurrent provision scenario would queue behind it. Its decline is *goal-driven* (cooperative persona + "decline if you'd wait" goal) — personas and goals compose.
 103: - **How to run:** `./agentic/run_smoke.sh spend_refusal` · `… long_job_30m` (expect ~20 min) · `… saturation` (solo) · ablation study: `python agentic/run_suite.py --scenarios happy_path,gated_provision --ablations none,skill --repeat 5`.
 104: 
 105: ### Provenance bundle per run (built 2026-07-07)
 106: Every run — pass, fail, or crash — leaves durable evidence in `agentic/runs/<runid>-<scenario>/` (volume-mounted through the `--rm` container; gitignored; written in a `finally` and never able to fail the run):
 107: - **`record.json`** — the resolved config that *actually ran* (templated prompt, persona+goal, model, effort, ablations, git SHA, pool user, endpoint name), grading verdicts (trace + world), rc, cost/usage/turns, redacted env, the human-sim dialogue.
 108: - **`messages.jsonl`** — the complete SDK message stream: assistant text, **thinking blocks** (as the API returns them — *summarized* on Opus 4.7+; an API property, not a harness limit), tool_use inputs, tool_results. This is the re-grading substrate: new/changed invariants and the future LLM-judge run **offline against stored bundles**, no agent re-run needed.
 109: - **`transcript.md`** — human-readable rendering (conversation + 🧠 thinking + tool calls + dialogue + grading).
 110: - **`claude-session/`** — the CLI's *native* session JSONLs harvested from inside the jail by `entrypoint.sh` — includes the **human-sim's own sessions**, so both actors' records are first-class.
 111: Deliberately pragmatic-first: a PROV-O/W3C-PROV mapping over `record.json` (agent/activity/entity per run) is a later layering, not a prerequisite.
 112: 
 113: ## Reuse meta-workflow & automated teardown
 114: `stop_endpoint` releases the *block* but leaves the login endpoint **online for reuse** — the SSH-once keystone. Two coupled needs the scenario matrix must handle:
 115: - **Reuse scenarios (stateful).** A key behaviour to test: a second `connect_facility` **reuses** a still-online endpoint (zero SSH) instead of re-bootstrapping. But reuse-vs-bootstrap is *internal* to hpc-bridge — invisible in the agent's tool calls. So (a) hpc-bridge should **surface reuse in the `connect_facility` result** (e.g. `reused: true` / a notice) so an invariant can assert it (small, generally-useful change), and (b) the harness needs **scenario setup/chaining** — leave an endpoint up, then run the reuse scenario against a **stable** endpoint name (a deliberate exception to the per-run-unique-name isolation).
 116: - **Automated pull-down — ✅ built.** `run.py._teardown` runs `gce stop`+`delete <name>` over SSH as the test user (control-plane, off the hot path; command validated live) in a `finally`, so a run cleans up even on failure. **Per-scenario configurable:** `TEARDOWN = delete | keep`, plus an optional stable `FACILITY_ID` so a reuse chain shares one endpoint name (vs the default per-run-unique `globus1-<runid>`). Reuse chains set `keep`. Still to build: the suite runner that sequences setup→reuse, and hpc-bridge surfacing `reused` so the reuse itself is assertable.
 117: 
 118: ## As-built jail gotchas (from the first live bring-up)
 119: Baked into `Dockerfile` / `entrypoint.sh` / `run_smoke.sh`, but worth knowing: **(1)** `python:3.11-slim` ships no compiler → `build-essential python3-dev` for `psutil` (pulled by `globus-compute-endpoint`); **(2)** Claude Code refuses `--dangerously-skip-permissions` (= `bypassPermissions`) as **root** → non-root `agent` user + an entrypoint that stages the root-owned mounted creds into agent-owned copies (SSH key `0600`; a *writable* `storage.db`); **(3)** `docker build -f agentic/Dockerfile … --provenance=false` (Dockerfile isn't at context root; provenance attestation tripped a buildkit snapshot-export glitch); **(4)** deps-layer split (`COPY pyproject.toml uv.lock` + `src/` → `uv sync` **before** `COPY .`) so code edits don't recompile `psutil`; **(5)** `run.py`/`runner.py` stream tool calls to stderr (progress was invisible while buffered).
 120: 
```
</details>


# ITEM 3

## pre_edit_fresh:Reference/Configuration.md|5b74dcb5
**pre_edit_fresh** · note `Reference/Configuration.md` · seq 21 · commit 5b74dcb5 · state fresh

**Q:** These anchored files changed but the note read FRESH. Did the change make any claim in the note wrong?


```diff
 src/hpc_bridge/server.py | 19 +++++++++++++++----
 1 file changed, 15 insertions(+), 4 deletions(-)

diff --git a/src/hpc_bridge/server.py b/src/hpc_bridge/server.py
index 21f04a9..5f33241 100644
--- a/src/hpc_bridge/server.py
+++ b/src/hpc_bridge/server.py
@@ -180,13 +180,18 @@ def _unsupported_entry_reason(entry) -> str | None:
     return None
 
 
-def _facility_from_entry(entry, *, account: str) -> Facility:
+def _facility_from_entry(entry, *, account: str, pinned_host: str | None = None) -> Facility:
     """Build a SlurmFacility from a catalog entry + per-user runtime values — shared by the startup
     path (make_facility) and the runtime path (connect_facility). `account` may be empty for the
-    agentic flow; ensure_endpoint_up(account=…) overrides it per scheduler block."""
+    agentic flow; ensure_endpoint_up(account=…) overrides it per scheduler block.
+
+    `pinned_host` overrides the entry's `ssh_host` and is passed ONLY on the env-pinned startup path
+    (HPC_BRIDGE_MACHINE + HPC_BRIDGE_SSH_HOST). The agentic connect path leaves it None so the BOUND
+    facility's own `ssh_host` is authoritative — a process-wide env must never silently redirect an
+    agent-chosen facility to a different host (the "globus1 is Aurora" trap, [#35])."""
     from .facility.remote import profile_from_catalog_entry
 
-    alias = os.environ.get("HPC_BRIDGE_SSH_HOST", "").strip() or entry.ssh_host
+    alias = pinned_host or entry.ssh_host
     # Login name: optional env override, else read live from ~/.ssh/config (`ssh -G`) — never a
     # *required* boot-env var. The key is deferred to the config's IdentityFile in _slurm_facility.
     user = os.environ.get("HPC_BRIDGE_SSH_USER", "").strip() or _ssh_config_user(alias)
@@ -210,7 +215,13 @@ async def _catalog_facility(machine: str) -> Facility:
     reason = _unsupported_entry_reason(entry)
     if reason:
         raise RuntimeError(f"{machine}: {reason}")
-    return _facility_from_entry(entry, account=_require_env("HPC_BRIDGE_ACCOUNT"))
+    # Startup pin only: HPC_BRIDGE_SSH_HOST may override the catalog's canonical ssh_host (your own
+    # alias / a login node, or the FQDN the container needs). The agentic connect path does NOT (#35).
+    return _facility_from_entry(
+        entry,
+        account=_require_env("HPC_BRIDGE_ACCOUNT"),
+        pinned_host=os.environ.get("HPC_BRIDGE_SSH_HOST", "").strip() or None,
+    )
 
 
 async def make_facility() -> Facility:
```

<details><summary>note</summary>

```
   1: # Configuration
   2: 
   3: > [!abstract] Role
   4: > The environment variables `make_facility` and `lifespan` ([[server]]) read at startup. Read **once** when the MCP server launches — change one ⇒ restart the session.
   5: 
   6: ## Facility selection
   7: 
   8: | Var | Effect |
   9: |---|---|
  10: | `HPC_BRIDGE_MACHINE` | A catalog machine id/subject (e.g. `anvil`) → resolve its profile from the [[Facility catalog|catalog]] at startup; unset → local dev (the agent can bind one at runtime via `connect_facility`). Machines are catalog *data*, never hardcoded. |
  11: | `HPC_BRIDGE_SEARCH_INDEX` | **Required for catalog discovery** — the Globus Search index UUID (run `hpc-bridge-catalog` once for the search scope). Unset → no catalog: a machine can't be resolved (a hard failure until agent-discovery lands). |
  12: | `HPC_BRIDGE_SSH_USER` · `HPC_BRIDGE_SSH_KEY` | **Optional overrides** — SSH login name + key. Unset ⇒ read live from your `~/.ssh/config` (`ssh -G` for the user, the config's `IdentityFile` for the key), so they needn't be exported into the already-running server's env. |
  13: | `HPC_BRIDGE_ACCOUNT` | Slurm charge account — **required only on the `HPC_BRIDGE_MACHINE` startup-pin path**; the agentic flow takes it from `connect_facility`'s allocations or you pass it to `ensure_endpoint_up`. |
  14: | `HPC_BRIDGE_SSH_HOST` | Override the SSH alias/host (else the catalog entry's `ssh_host`). |
  15: | `HPC_BRIDGE_SSH_CONTROL_PERSIST` | Seconds to keep the per-facility SSH **ControlMaster** alive (default `60`; `0` disables multiplexing) — one auth serves the whole bootstrap + discovery. |
  16: | `HPC_BRIDGE_RELEASE_ATTEMPTS` · `HPC_BRIDGE_RELEASE_BACKOFF_S` | `stop_endpoint`'s bounded retry to **confirm** the block cancel when the login release channel is cold (default `3` × `6`s). Exhausted → honest `status="draining"` (never a false `"down"`); see [[Cost control]] / #24. |
  17: | `HPC_BRIDGE_REMOTE_VENV` | Override the remote `globus-compute-endpoint` venv path (else the `/home/{user}/hpc-bridge/gce-venv` convention). |
  18: | `HPC_BRIDGE_PARTITION` | Default partition — the [[Resource shapes & the spend floor|gate]] overrides it per run. |
  19: 
  20: ## Session & cost
  21: 
  22: | Var | Effect |
  23: |---|---|
  24: | `HPC_BRIDGE_PROFILE` | `interactive` \| `batch` (default `batch`) — see [[profile]]. |
  25: | `HPC_BRIDGE_SCRATCH` | Override the [[Session continuity\|session-shell root]] (else the facility's `$SCRATCH`, else a local default). |
  26: | `HPC_BRIDGE_STATE_DIR` | Base dir for hpc-bridge's **local state** — login-node pins (`endpoints.json`), the local-discovery facility cache (`facilities.json`), and the SSH ControlMaster sockets. Default `~/.hpc-bridge`; relocating it isolates all state (the test suite points it at a tmp dir so tests never touch the real one). |
  27: | `HPC_BRIDGE_CHARGE_FACTOR` | The QOS SU multiplier for the [[Cost control\|spend clock]] (default `0.0` = free). |
  28: | `HPC_BRIDGE_SYNC_WAIT_S` | How long `run_shell` blocks for a result before handing back a poll handle (default `120`). A command still running past it comes back `running` + `task_id` (**not** cut); retrieve it with `poll_task`. Clamped strictly below the task ceiling. |
  29: | `HPC_BRIDGE_MAX_TASK_S` | Optional cap (seconds) on a single task before the worker kills it (exit 124). **Unset ⇒ the ceiling is the block walltime** — the deterministic default. Set it to bound the blast radius of a hung task on a long-walltime facility ([[Cost control]], [#21](https://github.com/ryanchard/hpc-bridge/issues/21)). |
  30: | `HPC_BRIDGE_USER_DIR` | Local `globus_compute` dir (set by `.mcp.json`). |
  31: 
  32: ## BYO endpoint
  33: 
  34: | Var | Effect |
  35: |---|---|
  36: | `HPC_BRIDGE_ENDPOINT_ID` | A UUID to dispatch to directly, skipping local provisioning. **Required on macOS/Windows**, where the local daemon can't run ([[endpoint]]). |
  37: 
  38: ## See also
  39: [[server]] · [[facility-remote]] · [[Plugin packaging]]
```
</details>


# ITEM 4

## pre_edit_fresh:Reference/Configuration.md|9a19ee11
**pre_edit_fresh** · note `Reference/Configuration.md` · seq 32 · commit 9a19ee11 · state fresh

**Q:** These anchored files changed but the note read FRESH. Did the change make any claim in the note wrong?


```diff
 src/hpc_bridge/server.py | 141 ++++++++++++++++++++++++++++++++++++++---------
 1 file changed, 116 insertions(+), 25 deletions(-)

diff --git a/src/hpc_bridge/server.py b/src/hpc_bridge/server.py
index bceaafb..158822c 100644
--- a/src/hpc_bridge/server.py
+++ b/src/hpc_bridge/server.py
@@ -56,6 +56,11 @@ class ShapeRuntime:
     # Set when user_endpoint_config changed under a live runner (e.g. a new partition): the
     # cached Executor captured the old config at build time, so _runner_for must rebuild it.
     runner_stale: bool = False
+    # A recorded NO-ACCOUNT refusal (the MEP could not map our identity). Sticky: later calls return
+    # it without re-submitting — a rapid re-submit got a transient RESOURCE_CONFLICT from the web
+    # service (live, 2026-09-03) that flipped the verdict back to 'allocating nodes…'. Cleared when the
+    # runtime is dropped (re-bind/teardown) or a new login lands (_forget_identity_verdicts).
+    no_account: str | None = None
     # Deterministic spend floor: a scheduler compute shape may not start a block until spend is
     # explicitly acknowledged via ensure_endpoint_up(confirm_spend=True). Persists for the
     # session once given (no re-nagging); cleared on stop/reset when the shape state is dropped.
@@ -317,21 +322,17 @@ def _make_search_client(_app_factory=None):
 
 
 def make_catalog():
-    """The runtime catalog is the Globus Search index (HPC_BRIDGE_SEARCH_INDEX). There is **no
-    bundled fallback**: a machine the index can't resolve is a hard failure (the soft
-    agent-discovery fallback is a later slice). The bundled seed is the curator's ingest source
+    """The runtime catalog is the PUBLIC REGISTRY — a Globus Search index, read anonymously. The
+    plugin ships its id (`PUBLIC_REGISTRY_INDEX`), so `list_facilities()` works out of the box with no
+    login and no configuration; HPC_BRIDGE_SEARCH_INDEX overrides it (a private/staging registry).
+    There is **no bundled fallback**: a machine the registry can't resolve is a hard failure (the
+    soft agent-discovery fallback is a later slice). The bundled seed is the curator's ingest source
     (see `hpc-bridge-catalog`), never a runtime catalog.
     """
-    index = os.environ.get("HPC_BRIDGE_SEARCH_INDEX", "").strip()
-    if not index:
-        raise RuntimeError(
-            "HPC_BRIDGE_SEARCH_INDEX is required: the catalog is the Globus Search index (the "
-            "bundled fallback was removed). Set it and run `hpc-bridge-catalog` once to grant the "
-            "search scope."
-        )
-    from .catalog.search import SearchCatalog
+    from .catalog.search import PUBLIC_REGISTRY_INDEX, SearchCatalog
 
-    client = _make_search_client()  # raises if the search scope isn't granted yet
+    index = os.environ.get("HPC_BRIDGE_SEARCH_INDEX", "").strip() or PUBLIC_REGISTRY_INDEX
+    client = _make_search_client()  # anonymous unless a Search-scoped login is already held
     cache_dir = (
         Path(os.environ.get("CLAUDE_PLUGIN_DATA", str(Path.home() / ".hpc-bridge")))
         / "catalog-cache"
@@ -547,6 +548,8 @@ async def _confirm_worker(app: AppCtx, shape: str, *, force: bool) -> str:
     also kicks that block). Within CANARY_TTL_S of the last success we trust warmth and skip
     the round-trip so an interactive burst doesn't pay it on every call."""
     rt = _shape_runtime(app, shape)
+    if rt.no_account:  # terminal for this identity: no canary, no runner rebuild — keep last_canary as the evidence
+        return "provisioning"
     runner = _runner_for(app, shape)
     now = time.monotonic()
     # A task still running on this shape IS liveness — the worker is demonstrably executing our work.
@@ -571,6 +574,8 @@ async def _confirm_worker(app: AppCtx, shape: str, *, force: bool) -> str:
         # forever (the #37 dead-end in a new guise). Rebuild it on the next call; the failure text
         # rides `last_canary` into the provisioning notice so the cause is visible, not buried.
         rt.runner_stale = True
+        if _no_account_failure(result.error):
+            rt.no_account = result.error
     return "provisioning"
 
 
@@ -851,6 +856,18 @@ async def _ensure_endpoint_up(
                 rt.provisioning_since = time.monotonic()
             provisioning_elapsed = time.monotonic() - rt.provisioning_since
             notice = f"allocating nodes on {active_partition!r}…" if active_partition else "allocating nodes…"
+            if rt.last_canary is not None and _no_account_failure(rt.last_canary.error):
+                # The manager refused to start a user endpoint for THIS identity: no local account. Not
+                # 'allocating nodes' — a terminal `down`, so the agent stops polling and tells the user.
+                from .login import globus_identity_label
+
+                identity = await asyncio.to_thread(globus_identity_label)
+                rt.provisioning_since = None
+                return EndpointStatus(
+                    status="down", block_state="cold", endpoint_id=eid, session_spend=spend,
+                    partition=active_partition, account=active_account,
+                    notice=_no_account_notice(app, rt.last_canary.error, identity),
+                )
             if not _has_login_shape(app) and rt.last_canary is None:
                 # On a MEP a canary runs on EVERY poll whose manager gate passes (and is recorded even
                 # when it fails), so "provisioning with no canary ever recorded" means the manager
@@ -925,6 +942,7 @@ async def _authenticate(app: AppCtx, force: bool = False, mode: str | None = Non
         return LoginStatus(phase="logged_in", notice="Globus login present with every scope hpc-bridge needs.")
     start, status = await _start_login_and_wait(flow, mode)
     if status == "done":
+        _forget_identity_verdicts(app)
         return LoginStatus(phase="logged_in", notice="Globus login completed in the browser; carry on.")
     return LoginStatus(phase="needs_login", login_url=start.login_url, login_mode=start.mode,
                        notice=_login_notice(start, flow.error,
@@ -940,6 +958,7 @@ async def _complete_login(app: AppCtx, code: str) -> LoginStatus:
     except Exception as exc:  # noqa: BLE001 - a bad/expired code is a structured outcome, not a crash
         return LoginStatus(phase="failed", notice=f"login code not accepted: {type(exc).__name__}: {exc}"[:300]
                            + " — call authenticate() for a fresh link.")
+    _forget_identity_verdicts(app)
     return LoginStatus(phase="logged_in", notice="Globus login complete. Continue: connect_facility again.")
 
 
@@ -968,8 +987,9 @@ async def complete_login(code: str, ctx: Context) -> LoginStatus:
 
 @mcp.tool()
 async def list_facilities(query: str = "") -> list[CatalogSummary]:
-    """List the HPC machines hpc-bridge can stand up, from the facility catalog (the Globus Search
-    index — set HPC_BRIDGE_SEARCH_INDEX). Empty query lists all; a query filters by name/description.
+    """List the HPC machines hpc-bridge can stand up, from the public facility registry (a Globus
+    Search index, read anonymously — works with no login). Empty query lists all; a query filters by
+    name/description.
 
     Returns agent-safe summaries (no executable config or raw UUIDs). Pick one and call
     connect_facility(facility=…) to bring up its login node and see your allocations. No SSH, no
@@ -1075,10 +1095,20 @@ async def _connect_facility(
             _facility_store().put(details.ssh_host, details.model_dump(mode="json"))
     else:
         entry = app.session_facilities.get(facility)
+        registry_error: Exception | None = None
+        if entry is None:
+            # THE REGISTRY WINS for any catalogued id (decision 2026-09-03: curated entries are the stable
+            # ones). Found live: the maintainer's local cache held an SSH-era `globus1` config that would
+            # have shadowed the registry's MEP entry and silently taken the SSH path.
+            try:
+                entry = await make_catalog().get(facility)
+            except Exception as exc:  # noqa: BLE001 - registry unreachable -> the cache may still serve
+                registry_error = exc
         if entry is None:
             # LOCAL DISCOVERY: a previously-confirmed BYO config for this host, cached to disk (keyed on
-            # ssh_host, canonical; facility id as fallback) — use it with NO SSH probe, then bootstrap
-            # reuses the online endpoint over the web. A stale/invalid cache falls through to catalog/probe.
+            # ssh_host, canonical; facility id as fallback) — only for facilities the registry does NOT
+            # know (or when it is unreachable). Used with NO SSH probe; bootstrap then reuses the online
+            # endpoint over the web. A stale/invalid cache falls through to the probe.
             cached = _facility_store().get(ssh_host or facility)
             if cached is not None:
                 try:
@@ -1086,15 +1116,12 @@ async def _connect_facility(
                     app.session_facilities[facility] = entry
                 except Exception:  # noqa: BLE001 - stale/invalid cached config
                     entry = None
-        if entry is None:
-            try:
-                entry = await make_catalog().get(facility)
-            except Exception as exc:  # noqa: BLE001 - index/scope unavailable -> ask/probe
-                return await _propose_or_ask(
-                    facility, ssh_host,
-                    f"catalog unavailable ({type(exc).__name__}); give me this facility's SSH host "
-                    "(ssh_host=… or HPC_BRIDGE_SSH_HOST) to probe it, or supply details= directly.",
-                )
+        if entry is None and registry_error is not None:
+            return await _propose_or_ask(
+                facility, ssh_host,
+                f"registry unavailable ({type(registry_error).__name__}); give me this facility's SSH "
+                "host (ssh_host=… or HPC_BRIDGE_SSH_HOST) to probe it, or supply details= directly.",
+            )
         if entry is None:
             return await _propose_or_ask(
                 facility, ssh_host,
@@ -1759,10 +1786,74 @@ def _dispatch_error_suffix(canary: CanaryResult | None) -> str:
… (74 more lines)
```

<details><summary>note</summary>

```
   1: # Configuration
   2: 
   3: > [!abstract] Role
   4: > The environment variables `make_facility` and `lifespan` ([[server]]) read at startup. Read **once** when the MCP server launches — change one ⇒ restart the session.
   5: 
   6: ## Facility selection
   7: 
   8: | Var | Effect |
   9: |---|---|
  10: | `HPC_BRIDGE_MACHINE` | A catalog machine id/subject (e.g. `anvil`) → resolve its profile from the [[Facility catalog|catalog]] at startup; unset → local dev (the agent can bind one at runtime via `connect_facility`). Machines are catalog *data*, never hardcoded. |
  11: | `HPC_BRIDGE_SEARCH_INDEX` | **Required for catalog discovery** — the Globus Search index UUID: ours is **`6ff95fb8-1113-42be-a811-3d1cb5a67bd5`** (see [[Facility catalog]] for what it holds). Run `hpc-bridge-catalog` once for the search scope. Unset → no catalog: a machine can't be resolved (a hard failure until agent-discovery lands). Locally it's set in `.claude/settings.local.json` (gitignored) — not in your interactive shell. |
  12: | `HPC_BRIDGE_SSH_USER` · `HPC_BRIDGE_SSH_KEY` | **Optional overrides** — SSH login name + key. Unset ⇒ read live from your `~/.ssh/config` (`ssh -G` for the user, the config's `IdentityFile` for the key), so they needn't be exported into the already-running server's env. |
  13: | `HPC_BRIDGE_ACCOUNT` | Slurm charge account — **required only on the `HPC_BRIDGE_MACHINE` startup-pin path**; the agentic flow takes it from `connect_facility`'s allocations or you pass it to `ensure_endpoint_up`. |
  14: | `HPC_BRIDGE_SSH_HOST` | Override the SSH host — **startup-pin path only** (`HPC_BRIDGE_MACHINE`): reach the catalog's canonical machine via your own `~/.ssh/config` alias / a specific login node / an FQDN (the container needs the FQDN — no ssh config). The agentic `connect_facility` path **ignores it** — the *bound* facility's own `ssh_host` is authoritative, so a stray/global env can't silently redirect an agent-chosen facility ([#35](https://github.com/ryanchard/hpc-bridge/issues/35)). It is also the discovery-probe host when you `connect_facility` without an `ssh_host`. |
  15: | `HPC_BRIDGE_SSH_CONTROL_PERSIST` | Seconds to keep the per-facility SSH **ControlMaster** alive (default `60`; `0` disables multiplexing) — one auth serves the whole bootstrap + discovery. |
  16: | `HPC_BRIDGE_RELEASE_ATTEMPTS` · `HPC_BRIDGE_RELEASE_BACKOFF_S` | `stop_endpoint`'s bounded retry to **confirm** the block cancel when the login release channel is cold (default `3` × `6`s). Exhausted → honest `status="draining"` (never a false `"down"`); see [[Cost control]] / #24. |
  17: | `HPC_BRIDGE_REMOTE_VENV` | Override the remote `globus-compute-endpoint` venv path (else the `/home/{user}/hpc-bridge/gce-venv` convention). |
  18: | `HPC_BRIDGE_PARTITION` | Default partition — the [[Resource shapes & the spend floor|gate]] overrides it per run. |
  19: 
  20: ## Session & cost
  21: 
  22: | Var | Effect |
  23: |---|---|
  24: | `HPC_BRIDGE_PROFILE` | `interactive` \| `batch` (default `batch`) — see [[profile]]. |
  25: | `HPC_BRIDGE_SCRATCH` | Override the [[Session continuity\|session-shell root]] (else the facility's `$SCRATCH`, else a local default). |
  26: | `HPC_BRIDGE_STATE_DIR` | Base dir for hpc-bridge's **local state** — login-node pins (`endpoints.json`), the local-discovery facility cache (`facilities.json`), and the SSH ControlMaster sockets. Default `~/.hpc-bridge`; relocating it isolates all state (the test suite points it at a tmp dir so tests never touch the real one). |
  27: | `HPC_BRIDGE_CHARGE_FACTOR` | The QOS SU multiplier for the [[Cost control\|spend clock]] (default `0.0` = free). |
  28: | `HPC_BRIDGE_SYNC_WAIT_S` | How long `run_shell` blocks for a result before handing back a poll handle (default `120`). A command still running past it comes back `running` + `task_id` (**not** cut); retrieve it with `poll_task`. Clamped strictly below the task ceiling. |
  29: | `HPC_BRIDGE_MAX_TASK_S` | Optional cap (seconds) on a single task before the worker kills it (exit 124). **Unset ⇒ the ceiling is the block walltime** — the deterministic default. Set it to bound the blast radius of a hung task on a long-walltime facility ([[Cost control]], [#21](https://github.com/ryanchard/hpc-bridge/issues/21)). |
  30: | `HPC_BRIDGE_USER_DIR` | Local `globus_compute` dir (set by `.mcp.json`). |
  31: | `HPC_BRIDGE_LOGIN_WAIT_S` | How long `connect_facility`/`authenticate` wait for a browser Globus login to land before returning `needs_login` (default 90). |
  32: 
  33: ## BYO endpoint
  34: 
  35: | Var | Effect |
  36: |---|---|
  37: | `HPC_BRIDGE_ENDPOINT_ID` | A UUID to dispatch to directly, skipping local provisioning. **Required on macOS/Windows**, where the local daemon can't run ([[endpoint]]). |
  38: 
  39: ## See also
  40: [[server]] · [[facility-remote]] · [[Plugin packaging]]
```
</details>


# ITEM 5

## at_risk:Modules/context.md|d05af709
**at_risk** · note `Modules/context.md` · seq 43 · commit d05af709 · state fresh

**Q:** These anchored files changed but the note read FRESH. Did the change make any claim in the note wrong?


```diff
 src/hpc_bridge/context.py | 19 +++++++++++++++++++
 1 file changed, 19 insertions(+)

diff --git a/src/hpc_bridge/context.py b/src/hpc_bridge/context.py
index 5994044..65a3791 100644
--- a/src/hpc_bridge/context.py
+++ b/src/hpc_bridge/context.py
@@ -18,6 +18,7 @@ from .lifecycle import EndpointState
 from .login import LoginFlow
 from .profile import Profile
 from .runner import CanaryResult, GlobusRunner
+from .shapes import SHAPES
 
 DEFAULT_SHAPE = "compute"
 
@@ -95,3 +96,21 @@ class AppCtx:
     login_flow: LoginFlow | None = None
     # serializes provision / runner-swap / teardown so concurrent tool calls can't race AppCtx state
     lock: asyncio.Lock = field(default_factory=asyncio.Lock)
+
+
+def _supported_shapes(app: AppCtx) -> tuple[str, ...]:
+    """The shapes the bound facility can serve. Default: every shape (a personal endpoint renders
+    our own template, which has both). A facility-run multi-user endpoint declares
+    `supported_shapes=("compute",)` — its schema REJECTS the LocalProvider login shape — and the
+    server derives the rest from that single fact: no login shape ⇒ no free channel for the
+    allocation listing / the pilot query / the scancel release ⇒ stop is draining-only, teardown is
+    a no-op, every shape is billed."""
+    return tuple(getattr(app.facility, "supported_shapes", None) or SHAPES)
+
+def _has_login_shape(app: AppCtx) -> bool:
+    return "login" in _supported_shapes(app)
+
+def _idle_release_s(app: AppCtx) -> int:
+    """The block's idle-release window: the facility's own (a MEP's template), else our profile's.
+    One source — the warm-block bounds note and the MEP stop notice used to read different ones."""
+    return int(getattr(app.facility, "max_idletime_s", None) or app.profile.max_idletime_s)
```

<details><summary>note</summary>

```
   1: # context
   2: 
   3: > [!abstract] Role
   4: > The server's runtime state as pure data: `AppCtx` (one per server, shared by every tool call), `ShapeRuntime` (per resource shape: Executor, warmth/canary, spend clock, the sticky no-account verdict), `TaskHandle` (a command still running past the sync-wait), and `DEFAULT_SHAPE`. No behaviour lives here.
   5: 
   6: Split step 1 of the [[Review 2026-09-03 — code quality|code-quality review]]'s plan (2026-09-03): a leaf module so the modules that follow (config, notices, warmth, tasks, …) can import the state without importing `server`. `server` re-exports the four names, so `from hpc_bridge.server import AppCtx` — every test and tool — keeps working. Field-level rationale comments moved with the fields.
   7: 
   8: ## See also
   9: [[server]] · [[shapes]] · [[lifecycle]] · [[runner]]
```
</details>


# ITEM 6

## at_risk:Planned/Cross-harness portability.md|7b20c03f
**at_risk** · note `Planned/Cross-harness portability.md` · seq 112 · commit 7b20c03f · state fresh

**Q:** These anchored files changed but the note read FRESH. Did the change make any claim in the note wrong?


```diff
 src/hpc_bridge/server.py | 45 ++++++++++++++++++++++++++++++++++++++++++++-
 1 file changed, 44 insertions(+), 1 deletion(-)

diff --git a/src/hpc_bridge/server.py b/src/hpc_bridge/server.py
index 1f58d3d..b8c72dd 100644
--- a/src/hpc_bridge/server.py
+++ b/src/hpc_bridge/server.py
@@ -5,6 +5,7 @@ import sys
 import time
 from collections.abc import AsyncIterator
 from contextlib import asynccontextmanager
+from pathlib import Path
 from typing import Literal
 
 from mcp.server.fastmcp import Context, FastMCP
@@ -177,10 +178,52 @@ async def lifespan(server: FastMCP) -> AsyncIterator[AppCtx]:
                 rt.runner.close()
 
 
+# --- operational guidance over MCP (cross-harness) --------------------------------------------------------------
+# hpc-bridge's operating guidance lives in the driving-hpc SKILL.md. Claude Code auto-loads it via its skill system;
+# other MCP hosts (hermes-agent, …) have no skill system, so we surface the same guidance over MCP itself:
+#   • a small always-on POINTER in `instructions=` (hosts that surface serverInfo.instructions inject it) telling the
+#     model to read the guidance RESOURCE before consequential actions — the lazy, Claude-Code-like path (a host loads
+#     the full text only when it's relevant), proven on hermes-on-ALCF and Claude Code (2026-09-05);
+#   • the full SKILL.md served VERBATIM as an @mcp.resource (one source, zero drift, paid for only when fetched).
+# Claude Code sets HPC_BRIDGE_OMIT_INSTRUCTIONS=1 in .mcp.json → no pointer for it (it has the skill; no duplication).
+_GUIDANCE_URI = "hpcbridge://guidance/operations"
+_SKILL_PATH = Path(__file__).resolve().parents[2] / "skills" / "driving-hpc" / "SKILL.md"
+_INSTRUCTIONS_POINTER = (
+    "These tools drive real HPC: stand up (or reuse) a Globus Compute endpoint on a login node, then run shell work "
+    "over it. Before you provision a billed compute block, present a spend gate, or handle a Globus/MFA login, READ "
+    f"the resource {_GUIDANCE_URI} and follow it — it carries the operating rules (select → discover → gate → "
+    "provision → wait; compute-only facilities; stop = draining vs down; never detach long jobs). If you cannot read "
+    "the resource, each tool's own description is the fallback."
+)
+
+
+def _guidance_text() -> str:
+    """The full driving-hpc guidance (SKILL.md) served verbatim as an MCP resource, for hosts without a skill system.
+    Resolved from the source tree; when hpc-bridge is published to PyPI, ship SKILL.md as package data and resolve it
+    here too (see the Cross-harness portability note)."""
+    try:
+        return _SKILL_PATH.read_text()
+    except OSError:
+        return ("hpc-bridge operational guidance is unavailable in this installation — rely on each tool's own "
+                "description. (The driving-hpc SKILL.md could not be located.)")
+
+
+def _server_instructions() -> str | None:
+    """The pointer, unless the host opts out (Claude Code, which loads the skill itself)."""
+    return None if config.omit_instructions() else _INSTRUCTIONS_POINTER
+
+
 # Named "endpoint", not "hpc-bridge" (the plugin/CLI name): Claude Code namespaces a plugin's MCP
 # tools as plugin:<plugin>:<server>, so matching names would read the doubled plugin:hpc-bridge:hpc-bridge.
 # Keep in sync with the mcpServers key in .mcp.json — CC namespaces by that key, this name just mirrors it.
-mcp = FastMCP("endpoint", lifespan=lifespan)
+mcp = FastMCP("endpoint", lifespan=lifespan, instructions=_server_instructions())
+
+
+@mcp.resource(_GUIDANCE_URI, name="driving-hpc operational guidance", mime_type="text/markdown")
+def _operations_guidance() -> str:
+    """The full hpc-bridge operating guidance (the driving-hpc skill) — how to select → discover → gate → provision →
+    wait, compute-only facilities, stop semantics, and the long-job rule. Read it before consequential actions."""
+    return _guidance_text()
 
 
 async def _ensure_endpoint_up(
```

<details><summary>note</summary>

```
   1: # Cross-harness portability
   2: 
   3: > [!abstract] In one line
   4: > hpc-bridge's core is already a host-neutral MCP server, so making it work beyond Claude Code — Claude Desktop, OpenAI's Agents SDK, NousResearch's hermes-agent, pi.dev's Pi — is mostly packaging plus giving the [[driving-hpc|SKILL.md guidance]] a host-agnostic delivery channel. The spend gate is already server-enforced, so it rides every host's own approval UI unchanged. Investigation run 2026-09-05 (a 7-agent workflow); this note is the design record.
   5: 
   6: ## The finding
   7: 
   8: The [[server|MCP server]] is a plain `FastMCP("endpoint", lifespan=lifespan)` speaking stdio JSON-RPC, with **zero Anthropic-specific code** in its dependency graph (`mcp`, `pydantic`, `pyyaml`, `globus-sdk`, `globus-compute-sdk`) or in its twelve `@mcp.tool()` registrations. It is launched by the `hpc-bridge` console script, so `uvx hpc-bridge` starts it identically to how [[Plugin packaging|.mcp.json]] does. Any standard MCP client can spawn it.
   9: 
  10: Everything Claude-Code-specific is **install chrome** that translates or drops per host with no server change:
  11: 
  12: | surface | file | maps to elsewhere |
  13: |---|---|---|
  14: | plugin manifest | `.claude-plugin/plugin.json` | nothing — a non-CC host points its own MCP config at the console script |
  15: | launch stanza | `.mcp.json` (`${CLAUDE_PLUGIN_ROOT}`/`${CLAUDE_PLUGIN_DATA}`) | the host's own `mcpServers` entry with the vars resolved to literal paths |
  16: | PATH shim | `bin/run-with-uv` | unneeded on any host that launches subprocesses with a normal login PATH |
  17: | slash command | `commands/hpc-connect.md` | a system-prompt fragment, or an `@mcp.prompt` (the server defines none today) |
  18: | credential guard | `hooks/hooks.json` + `credential-guard.sh` | the host's own middleware, or nothing — better as an in-process check in `run_shell` |
  19: | standing guidance | `skills/driving-hpc/SKILL.md` | `instructions=` / `@mcp.resource` / tool docstrings (see below) |
  20: 
  21: Only **two levers** actually gate portability:
  22: 
  23: 1. **The guidance.** [[driving-hpc|SKILL.md]]'s ~93 lines of cross-tool orchestration (select → discover → gate → provision → wait; the compute-only-MEP exception set; the don't-detach-long-jobs rule [#21]; stop's draining-vs-down semantics) have **no MCP-native distribution today** — a grep confirms zero `@mcp.prompt`, `@mcp.resource`, or `instructions=` anywhere in `src/`. None of it lives in individual tool docstrings either.
  24: 2. **The spend gate.** Already enforced **server-side** ([[Resource shapes & the spend floor|confirm_spend]]): a billed shape without `confirm_spend=True` returns `needs_confirmation` and starts nothing. This is protocol-independent, so every host's generic "approve this tool call" surface serves as the human-in-the-loop ask with **no server change**.
  25: 
  26: ## Portability matrix
  27: 
  28: > [!note] Effort assumes the core stays an unmodified MCP server.
  29: 
  30: | harness | MCP | guidance channel | gating | effort | verdict |
  31: |---|---|---|---|---|---|
  32: | **Claude Code** (baseline) | native stdio via `.mcp.json` | CC Skill auto-injects SKILL.md | server floor + PreToolUse hook | — | reference impl (0.1.14, beta) |
  33: | **OpenAI Agents SDK** (self-hosted) | `MCPServerStdio` spawns it unchanged | `Agent.instructions` string only | server floor (+ optional `needs_approval`) | **low** | cheapest true non-Anthropic port |
  34: | **Claude Desktop** | native; manual `claude_desktop_config.json` today, `.mcpb` later | no atomic bundle; tool descriptions + result text | server floor + Desktop Auto/On-demand approve | **medium** | works today by hand; `.mcpb` a nicety |
  35: | **hermes-agent** (NousResearch) | native, stdio + HTTP; elicitation | native Skills system + `HERMES.md`/`CLAUDE.md` | docstring convention today; elicitation possible | **low** | best fit on paper — but env/SSH passthrough unproven |
  36: | **pi.dev Pi Coding Agent** | third-party adapters only; no native | per-tool `promptSnippet` + separate skills | **no built-in approval gate** | **medium** | plausible but unofficial; needs a spike |
  37: | **OpenAI hosted** (ChatGPT/Codex/Responses) | hosted `mcp` tool is **HTTP-only** | `Agent.instructions` | `require_approval` + callback | **high** | needs a Secure MCP Tunnel sidecar + looser secrets boundary — defer |
  38: 
  39: ## Recommended abstraction — one codebase, all hosts
  40: 
  41: 1. **`instructions=`** — add a compressed always-on core of SKILL.md to `FastMCP("endpoint", instructions=…)`. It is the one MCP-native field most hosts auto-inject into the system prompt.
  42: 2. **`@mcp.resource`** — expose the full reference material (`hpcbridge://guidance/operations`) for hosts that render resources, with `instructions=` telling the model to fetch it when unsure.
  43: 3. **Docstrings + result text** — push every individually load-bearing warning (spend-floor discipline, [[Endpoint reuse and MEP integration|endpoint-naming collisions]], the [#21] idle-release rule) into the specific tool's docstring and what it says back. This is the **only channel every surveyed host guarantees**.
  44: 4. **Keep `confirm_spend` server-side.** Do not move it onto MCP elicitation (which is in active protocol churn); optionally add an elicitation path later behind a capability probe, as a strict enhancement that falls back to the current return-and-recall convention.
  45: 5. **Decouple distribution** — publish `hpc-bridge` to **PyPI** so every host converges on `{"command": "uvx", "args": ["hpc-bridge"]}`, and author a spec-native `server.json`. Keep `.claude-plugin/*` + `.mcp.json` as a thin CC wrapper around the same console script, never a fork.
  46: 6. **Generated guidance exports** — maintain one source guidance doc and generate each host's form (compressed `instructions=`, the resource doc, a hermes-agent Skill) from it, the same anti-drift discipline as the [[Vault style guide|vault]]/HANDOFF split.
  47: 7. **Promote the credential guard** from a CC-only hook into an in-process check inside `run_shell`/`login_shell`, so every host gets the same defense-in-depth.
  48: 
  49: ## Phased plan (cheapest, highest-leverage first)
  50: 
  51: - **Phase 1 — protocol-native guidance + the cheap ports.** Add `instructions=` (compressed core), one or two `@mcp.resource`s, and audit tool docstrings/result text for the load-bearing warnings; publish to PyPI + author `server.json`. Validate end-to-end on the **OpenAI Agents SDK** (`MCPServerStdio`) and **Claude Desktop** (manual config) — both take the unmodified server. → guidance parity with zero per-host code; two non-CC harnesses verified.
  52: - **Phase 2 — Desktop packaging + hermes-agent.** Build a Claude Desktop `.mcpb`; wire `hermes mcp add`, enumerate the full `HPC_BRIDGE_*` env allowlist, and **empirically verify** whether `SSH_AUTH_SOCK`/a ControlMaster path passes through for the [[MFA and interactive SSH auth|MFA bootstrap]] (hermes-agent does **not** inherit ambient shell env for stdio servers). Test the hermes-agent Skills install for the guidance. → one-click Desktop install; hermes-agent's riskiest unknown resolved.
  53: - **Phase 3 — Pi spike.** Connect through an existing third-party pi-mcp adapter against a fake-cluster-tier instance, exercising a long-running `run_shell` + `poll_task` cycle and the `confirm_spend` round-trip in Pi's interactive TUI (Pi has **no built-in approval gate**, so the relay only works interactively). → an empirical answer on whether an unofficial adapter is production-viable.
  54: - **Phase 4 — OpenAI hosted (demand-gated, not scheduled).** Only if there is named demand for ChatGPT/Codex/Responses specifically: stand up Secure MCP Tunnel's `tunnel-client` as a new always-on sidecar and re-examine the per-call auth trust boundary against the local-creds design.
  55: 
  56: ## Risks
  57: 
  58: - **`instructions=` is implementation-defined**, not guaranteed — confirmed dropped by some clients (langchain4j, mcporter). The docstring/result-text duplication is the mitigation, not polish.
  59: - **Elicitation/sampling protocol churn** — the 2026-07-28 spec deprecates sampling/roots/logging over 12 months and restructures elicitation; FastMCP's `ctx.elicit()` already raises on 2026-07-28 connections without legacy mode. Any future elicitation work must version-detect. The server-enforced gate sidesteps this entirely.
  60: - **hermes-agent env inheritance** — stdio servers get an explicit allowlist + a fixed baseline only; whether `SSH_AUTH_SOCK`/ControlMaster passes through is unconfirmed. If not, the external-terminal MFA/SSH bootstrap could silently degrade there.
  61: - **Pi's MCP is unofficial** (third-party adapters, an open first-party tracking issue) and it has **zero native approval gate** — `confirm_spend`'s relay silently no-ops under headless/RPC embedding unless deliberately wired.
  62: - **OpenAI hosted** needs public HTTPS (conflicts with local-creds) or the tunnel sidecar, plus a looser trust boundary (bearer tokens transiting OpenAI's infra per call).
  63: - **No host bundles server + guidance atomically** — every non-CC host reintroduces a doc-drift burden across N guidance copies unless the generated-export discipline is actually adopted and owned.
  64: - **Tool-count ceilings** are soft (~30–50 tools before selection quality degrades). hpc-bridge's twelve are safe, but the margin narrows if more guidance gets folded into docstrings — re-check before the tool count grows.
  65: 
  66: ## Open questions
  67: 
  68: - **Referents confirmed (2026-09-05):** "Hermes" = **NousResearch/hermes-agent** (the runnable harness), "Pi" = **pi.dev's Pi Coding Agent** (earendil-works), not Inflection's pi.ai.
  69: - How much of SKILL.md is truly must-reach-every-host versus nice-to-have-on-request? This sizes how aggressively to compress into `instructions=` (a per-session token cost on every host) versus deferring to `@mcp.resource`.
  70: - Is a Desktop `.mcpb` worth building now, or does hand-editing `claude_desktop_config.json` cover the realistic near-term audience (people already comfortable with SSH/HPC/uv)?
  71: - Pursue official MCP-registry listing now, or is PyPI publication alone (enabling `uvx hpc-bridge` everywhere) the higher-value near-term step, with registry listing deferred until a host ships native registry browsing?
  72: - Who owns keeping the N per-host guidance copies in sync once this expands past Claude Code? The generated-export mechanism needs an owner before the second host ships.
  73: 
  74: ## See also
  75: 
  76: - [[V1 release]] — the current Claude-Code-plugin sprint (this is the direction *after* V1)
  77: - [[Plugin packaging]] — the CC-specific surfaces this note would translate
  78: - [[driving-hpc]] — the SKILL.md guidance that needs a host-agnostic channel
  79: - [[Resource shapes & the spend floor]] — why the gate is already portable
```
</details>


# ITEM 7

## at_risk:Reference/Using hpc-bridge with hermes-agent.md|7b20c03f
**at_risk** · note `Reference/Using hpc-bridge with hermes-agent.md` · seq 112 · commit 7b20c03f · state fresh

**Q:** These anchored files changed but the note read FRESH. Did the change make any claim in the note wrong?


```diff
 src/hpc_bridge/config.py |  9 +++++++++
 src/hpc_bridge/server.py | 45 ++++++++++++++++++++++++++++++++++++++++++++-
 2 files changed, 53 insertions(+), 1 deletion(-)

diff --git a/src/hpc_bridge/config.py b/src/hpc_bridge/config.py
index 03562da..49567b6 100644
--- a/src/hpc_bridge/config.py
+++ b/src/hpc_bridge/config.py
@@ -35,6 +35,15 @@ def search_index() -> str:
     return env("HPC_BRIDGE_SEARCH_INDEX") or PUBLIC_REGISTRY_INDEX
 
 
+def omit_instructions() -> bool:
+    """Suppress the MCP `instructions` guidance pointer. A host that already delivers the driving-hpc guidance by
+    another route sets HPC_BRIDGE_OMIT_INSTRUCTIONS=1 — Claude Code does, in .mcp.json, because it loads the skill —
+    so it gets no pointer (no duplication, no extra tokens). Every other host leaves it unset and gets the pointer,
+    then fetches the full guidance resource on demand (the lazy, Claude-Code-like path)."""
+    v = env("HPC_BRIDGE_OMIT_INSTRUCTIONS")
+    return v is not None and v.strip().lower() not in ("", "0", "false", "no", "off")
+
+
 def catalog_file() -> str | None:
     """A LOCAL catalog (seed-format YAML file or directory) that replaces the registry entirely — a dev/test seam:
     the agentic fake cluster's facility MEPs get fresh UUIDs per cluster and cannot live in the public registry, and a
diff --git a/src/hpc_bridge/server.py b/src/hpc_bridge/server.py
index 1f58d3d..b8c72dd 100644
--- a/src/hpc_bridge/server.py
+++ b/src/hpc_bridge/server.py
@@ -5,6 +5,7 @@ import sys
 import time
 from collections.abc import AsyncIterator
 from contextlib import asynccontextmanager
+from pathlib import Path
 from typing import Literal
 
 from mcp.server.fastmcp import Context, FastMCP
@@ -177,10 +178,52 @@ async def lifespan(server: FastMCP) -> AsyncIterator[AppCtx]:
                 rt.runner.close()
 
 
+# --- operational guidance over MCP (cross-harness) --------------------------------------------------------------
+# hpc-bridge's operating guidance lives in the driving-hpc SKILL.md. Claude Code auto-loads it via its skill system;
+# other MCP hosts (hermes-agent, …) have no skill system, so we surface the same guidance over MCP itself:
+#   • a small always-on POINTER in `instructions=` (hosts that surface serverInfo.instructions inject it) telling the
+#     model to read the guidance RESOURCE before consequential actions — the lazy, Claude-Code-like path (a host loads
+#     the full text only when it's relevant), proven on hermes-on-ALCF and Claude Code (2026-09-05);
+#   • the full SKILL.md served VERBATIM as an @mcp.resource (one source, zero drift, paid for only when fetched).
+# Claude Code sets HPC_BRIDGE_OMIT_INSTRUCTIONS=1 in .mcp.json → no pointer for it (it has the skill; no duplication).
+_GUIDANCE_URI = "hpcbridge://guidance/operations"
+_SKILL_PATH = Path(__file__).resolve().parents[2] / "skills" / "driving-hpc" / "SKILL.md"
+_INSTRUCTIONS_POINTER = (
+    "These tools drive real HPC: stand up (or reuse) a Globus Compute endpoint on a login node, then run shell work "
+    "over it. Before you provision a billed compute block, present a spend gate, or handle a Globus/MFA login, READ "
+    f"the resource {_GUIDANCE_URI} and follow it — it carries the operating rules (select → discover → gate → "
+    "provision → wait; compute-only facilities; stop = draining vs down; never detach long jobs). If you cannot read "
+    "the resource, each tool's own description is the fallback."
+)
+
+
+def _guidance_text() -> str:
+    """The full driving-hpc guidance (SKILL.md) served verbatim as an MCP resource, for hosts without a skill system.
+    Resolved from the source tree; when hpc-bridge is published to PyPI, ship SKILL.md as package data and resolve it
+    here too (see the Cross-harness portability note)."""
+    try:
+        return _SKILL_PATH.read_text()
+    except OSError:
+        return ("hpc-bridge operational guidance is unavailable in this installation — rely on each tool's own "
+                "description. (The driving-hpc SKILL.md could not be located.)")
+
+
+def _server_instructions() -> str | None:
+    """The pointer, unless the host opts out (Claude Code, which loads the skill itself)."""
+    return None if config.omit_instructions() else _INSTRUCTIONS_POINTER
+
+
 # Named "endpoint", not "hpc-bridge" (the plugin/CLI name): Claude Code namespaces a plugin's MCP
 # tools as plugin:<plugin>:<server>, so matching names would read the doubled plugin:hpc-bridge:hpc-bridge.
 # Keep in sync with the mcpServers key in .mcp.json — CC namespaces by that key, this name just mirrors it.
-mcp = FastMCP("endpoint", lifespan=lifespan)
+mcp = FastMCP("endpoint", lifespan=lifespan, instructions=_server_instructions())
+
+
+@mcp.resource(_GUIDANCE_URI, name="driving-hpc operational guidance", mime_type="text/markdown")
+def _operations_guidance() -> str:
+    """The full hpc-bridge operating guidance (the driving-hpc skill) — how to select → discover → gate → provision →
+    wait, compute-only facilities, stop semantics, and the long-job rule. Read it before consequential actions."""
+    return _guidance_text()
 
 
 async def _ensure_endpoint_up(
```

<details><summary>note</summary>

```
   1: # Using hpc-bridge with hermes-agent
   2: 
   3: > [!abstract] In one line
   4: > hpc-bridge is a standard MCP server, so any MCP host can drive it — not just Claude Code. This is the recipe for **NousResearch hermes-agent**, including using **ALCF's inference service** (or any model) as the operator, verified live 2026-09-05 (gpt-oss-120b on ALCF called `list_facilities` and got back `delta, globus-labs, anvil, expanse`). See [[Cross-harness portability]] for the design behind this.
   5: 
   6: ## Prerequisites
   7: 
   8: - **hermes-agent** installed (`curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`; `hermes` lands on `~/.local/bin`).
   9: - **A model.** Any OpenAI- or Anthropic-compatible provider hermes supports works. The Claude Pro/Max **subscription may not be used in hermes** (Anthropic restricts the OAuth token to Claude Code / Claude.ai, April 2026) — use an API key, or a facility inference service. This guide uses **ALCF** (Globus-authed, OpenAI-compatible) — see below.
  10: - **uv** (hermes bundles one at `~/.hermes/bin/uv`; hpc-bridge is launched through it).
  11: 
  12: ## 1. Point hermes at a model
  13: 
  14: For ALCF's inference service, the working `~/.hermes/config.yaml` model block (set the last three via `hermes config set`, not a hand-edit — see gotchas):
  15: 
  16: ```yaml
  17: model:
  18:   provider: custom
  19:   base_url: https://inference-api.alcf.anl.gov/resource_server/sophia/vllm/v1
  20:   api_key: ${ALCF_INFERENCE_TOKEN}   # env interpolation; hermes' inline key_env is NOT honored
  21:   default: openai/gpt-oss-120b
  22:   streaming: false                   # ALCF's gateway SSE isn't clean → 'empty stream' without this
  23:   context_length: 131072             # ALCF 404s on /v1/models, so auto-detect fails; set explicitly
  24:   max_tokens: 4096
  25: ```
  26: 
  27: ALCF access tokens last 24 h. Use the repo's **`scripts/hermes-alcf`** launcher (symlink it onto your PATH as `hermes-alcf`) — it mints a fresh token into `ALCF_INFERENCE_TOKEN` and execs `hermes`, so the expiry is invisible. One-time: `uv run --directory <repo> --extra integration python agentic/harness/inference_auth_token.py authenticate`.
  28: 
  29: > [!warning] hermes config gotchas (ALCF / any custom OpenAI-compatible endpoint)
  30: > - `api_key: ${VAR}` (interpolation) — the inline `key_env:` was ignored, causing a 401.
  31: > - `streaming: false` — else 'Provider returned an empty stream'.
  32: > - `context_length` + `max_tokens` **via `hermes config set model.context_length 131072`** — a raw hand-edit didn't take; because ALCF 404s on `/v1/models`, hermes can't auto-detect the window and reports 'Context length exceeded (N tokens)'.
  33: 
  34: ## 2. Add hpc-bridge as an MCP server
  35: 
  36: hermes does **not** inherit your shell environment for stdio MCP servers — only an explicit `env` allowlist plus a safe baseline — so list what hpc-bridge needs. Until hpc-bridge is on PyPI, launch it from the repo via `uv run`; afterwards this becomes `--command uvx --args hpc-bridge`.
  37: 
  38: ```bash
  39: hermes mcp add hpc-bridge \
  40:   --command "$(command -v uv)" \
  41:   --connect-timeout 180 \
  42:   --env HOME=$HOME HPC_BRIDGE_USER_DIR=$HOME/.hpc-bridge/hermes \
  43:   --args run --directory /path/to/hpc-bridge --extra integration hpc-bridge
  44: # answer 'y' to enable all 12 tools; `hermes mcp list` to confirm
  45: ```
  46: 
  47: For driving a **real facility** (not just `list_facilities`, which is unauthenticated), hpc-bridge also needs your Globus login (`~/.globus_compute/storage.db`) and SSH config (`~/.ssh`) — both under `$HOME`, so the `HOME` allowlist entry covers them. Add `HPC_BRIDGE_SEARCH_INDEX=<index>` to the `env` only if you use a non-default registry.
  48: 
  49: ## 3. Verify
  50: 
  51: ```bash
  52: hermes mcp test hpc-bridge     # should discover 12 tools
  53: hermes-alcf -z "Call the hpc-bridge list_facilities tool and list the facility ids."
  54: ```
  55: 
  56: Expected: the operator model calls `list_facilities` and reports the registry entries. This confirms the wiring without any facility or credentials.
  57: 
  58: ## Known gap — the operational guidance
  59: 
  60: Claude Code auto-injects hpc-bridge's [[driving-hpc|SKILL.md]] (the select → discover → gate → provision → wait orchestration, the compute-only-MEP rules, stop semantics). **hermes does not get this yet** — it sees the tools and their docstrings only. For `list_facilities` that's fine; for provisioning and the spend gate it matters. Until hpc-bridge ships the guidance over MCP (`instructions=` / `@mcp.resource`, see [[Cross-harness portability]]), a hermes user should paste the SKILL.md content into a `HERMES.md` or a hermes Skill. Closing this gap is the next step toward first-class hermes support.
  61: 
  62: ## See also
  63: 
  64: - [[Cross-harness portability]] — the design: what's host-neutral, the abstraction, the phased plan
  65: - [[driving-hpc]] — the guidance that needs a host-agnostic channel
  66: - [[The MCP tools]] — the twelve tools hermes discovers
```
</details>


# ITEM 8

## ep:Modules/server.md|2026-09-23T01:00:38Z|sha256:a4027|src/hpc_bridge/server.py#_run_shell
**episode** · note `Modules/server.md` · seq 39 · commit 426ff71d · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#_run_shell` _run_shell — **body**  (note lines [17])
  ```
  was: async def _run_shell(
    app: AppCtx, command: str, session_id: str = "default", shape: str = DEFAULT_SHAPE
) -> ShellOutcome:
    if reject := _shape_reject(app, shape):
        return _shape_reject_outcome(reject)
    session = Session(session_id, app.scratch_root)  # validates session_id before provisioning
    busy = None
    async with app.lock:  # provision + bind the runner atomically (no race with a concurrent stop)
        not_warm = await _ensure_warm_runner(app, shape)
        runner = _shape_runtime(app, shape).runner
        if not_warm is None:
            busy = _busy_session(a
  ---
  now: async def _run_shell(
    app: AppCtx, command: str, session_id: str = "default", shape: str = DEFAULT_SHAPE
) -> ShellOutcome:
    ready = await _ready_session(app, shape, session_id)
    if isinstance(ready, ShellOutcome):
        return ready
    runner, session = ready
    wrapped = session_shell.wrap(command, session)
    fut = runner.submit(wrapped)  # submit; wait a bounded time OFF the lock, else hand back a handle
    try:
        res = await asyncio.to_thread(fut.result, runner.timeout)
    except TimeoutError:  # still running past the sync-wait -> a poll handle, NOT a kill
        
  ```

<details><summary>note</summary>

```
   1: # server.py
   2: 
   3: > [!abstract] Role
   4: > The FastMCP server — the agent-facing entry point. Declares the **eleven** MCP tools, holds session state (`AppCtx`), gates on the Globus login, selects/binds the facility (SSH personal endpoint or facility MEP), and runs the provision → canary → dispatch → spend flow under a lock.
   5: 
   6: ## What it does
   7: 
   8: `server.py` is the runtime heart. It exposes eleven tools ([[The MCP tools]]), each a thin `@mcp.tool()` wrapper over a private `_`-helper that takes the `AppCtx`:
   9: 
  10: | Tool | Helper | Does |
  11: |---|---|---|
  12: | `list_facilities` | `_list_facilities` | browse the public registry ([[Facility catalog]]) — anonymous, agent-safe summaries with `access`/`access_note` |
  13: | `connect_facility` | `_connect_facility` | **login gate first**, then resolve (details → registry → cache → probe) and bind: bring up the login shape + list allocations (SSH), or attach with zero SSH (`_connect_mep`) |
  14: | `authenticate` | `_authenticate` | the Globus login gate as a tool: arm a login (browser loopback / paste), wait, report `LoginStatus` |
  15: | `complete_login` | `_complete_login` | finish a paste-mode login with the one-time auth code |
  16: | `ensure_endpoint_up` | `_ensure_endpoint_up` | provision/probe; report warm via the canary; thread account/partition; surface pilot state, dispatch failures, the terminal NO ACCOUNT |
  17: | `run_shell` | `_run_shell` | dispatch a command to the warm block / login shape; hand back a poll handle past the sync-wait |
  18: | `poll_task` | `_poll_task` | retrieve a long task's result; ORPHANED when its endpoint is gone |
  19: | `reset_session` | `_reset_session` | clear a session's cwd/env |
  20: | `stop_endpoint` | `_stop_endpoint` / `_stop_mep` | release the block over AMQP and leave the manager online (SSH), or drain honestly (MEP) |
  21: | `teardown_endpoint` | `_teardown_endpoint` | fully destroy the endpoint (`gce stop` + delete over SSH) — or, on a MEP, detach |
  22: | `login_shell` | `_login_shell` | read-only login-node command over SSH (cold-start escape hatch); refused on a MEP |
  23: 
  24: (Helpers carry the logic; the `@mcp.tool()` wrappers are thin. Exact line numbers drift — grep the symbol.)
  25: 
  26: ## How it works
  27: 
  28: - **State.** `AppCtx` (`:85`) holds the facility, profile, endpoint state, the per-shape `ShapeRuntime` (`:44` — its Executor, canary result, spend clock, the sticky `no_account` verdict, `spend_confirmed`), the live `TaskHandle`s (`:71`), the session-local facilities dict, the `LoginFlow` ([[login]]), and an `asyncio.Lock`. `lifespan` (`:423`) builds it from `make_facility` + env and installs the real `LoginFlow`.
  29: - **The Globus login gate.** `_connect_facility` (`:1115`) checks `login_flow.login_required()` **before the catalog read and before any SSH** — every non-`unsupported` outcome needs Globus, and constructing the SDK `Client` for the catalog on a fresh install would run the SDK's *own* command-line login on the MCP transport. `_start_login_and_wait` (`:1313`) arms the flow and, in browser mode, **waits** `_login_wait_s()` (`:1306`, `HPC_BRIDGE_LOGIN_WAIT_S` = 90 s) for the redirect to land — then the connect simply continues; a browser attempt that fails during the wait is re-armed in paste mode. Otherwise `_needs_login_result` (`:1355`) returns `phase="needs_login"` with the URL and the agent-facing instructions (`_login_notice`, `:1327`: relay the link, single-use, never a password). `_authenticate` (`:989`) / `_complete_login` (`:1004`) are the same flow as tools; both call `_forget_identity_verdicts` (`:1856`) on success — a new login may be a different identity, so sticky no-account verdicts are dropped and runners rebuilt.
  30: - **Facility selection.** `make_facility` (`:315`) returns a facility resolved from the [[Facility catalog|registry]] (`HPC_BRIDGE_MACHINE`, via `_catalog_facility` `:282`) or a `LocalFacility`. `_facility_from_entry` (`:248`) is the shared seam: a `compute_mep_uuid` entry → `MEPFacility` ([[facility-mep]]) — **MEP wins**; else `profile_from_catalog_entry` + `_slurm_facility` (`:203`), which reads the login-node pin from [[state]] and rebinds the CLI to it. `make_catalog` (`:373`) reads the registry with a **built-in** id (`PUBLIC_REGISTRY_INDEX`; `HPC_BRIDGE_SEARCH_INDEX` overrides) through `_make_search_client` (`:345`) — **anonymous** unless the Compute identity already holds the Search scope; it never triggers a login. `lifespan` **boots resiliently** — a failed `make_facility` (stale env, no registry) warns and starts unbound rather than crashing; `connect_facility` then binds and **moves `scratch_root`** to the facility (`_resolve_scratch_root`, `:331`, [[Session continuity]]). `HPC_BRIDGE_SSH_HOST` overrides the SSH host **only on this startup-pin path** (`_facility_from_entry(pinned_host=…)`); the agentic `connect_facility` path uses the *bound* facility's own `ssh_host`, so a global env can't silently redirect an agent-chosen facility ([#35](https://github.com/ryanchard/hpc-bridge/issues/35)).
  31: - **Resolution precedence in `_connect_facility`.** An explicit `details=` is a (re)definition and overrides everything (and is cached to `facilities.json` via `_facility_store`, `:1063`); else a session-local entry; else **the registry** (`make_catalog().get`); else the local BYO cache (`FacilityStore`, keyed on `ssh_host` — only for ids the registry doesn't know, or when it is unreachable); else `_propose_or_ask` (`:1394`). The registry wins for any catalogued id (decision 2026-09-03, [#49](https://github.com/ryanchard/hpc-bridge/issues/49): a stale SSH-era `globus1` cache would have shadowed the MEP entry).
  32: - **Un-indexed discovery.** `_propose_or_ask` builds a bare `SshTarget` (SSH user from `_ssh_config_user` / `ssh -G`, `:118`; key + host from `~/.ssh/config` + env) and runs the [[discovery]] probe → `proposed_facility_details`, or `needs_preauth` (`_needs_preauth_result`, `:1366`, carrying `preauth_command` — [[MFA and interactive SSH auth]]). On confirm, `_entry_from_details` (`:1071`) builds a session-local entry whose endpoint name comes from `_session_endpoint_name` (`:1052`) — `hpc-bridge-<ssh_host slug>`, keyed on the SSH host (`HPC_BRIDGE_ENDPOINT_NAME` overrides it for harness run isolation). `_control_settings` (`:136`) configures the shared ControlMaster ([[facility-remote]]), with `_short_control_dir` (`:161`) keeping the socket path under the Unix cap.
  33: - **Two kinds of bind.** After the bind, `_connect_facility` asks `_has_login_shape` (`:485`, from `_supported_shapes` `:475` — `getattr(facility, "supported_shapes", SHAPES)`). With a login shape it provisions `login`, then runs the allocation command over Compute → `needs_account`; a bootstrap SSH failure is rewritten by `_explain_provision_error` (`:170`) into `NO SSH ACCESS to <host> as <user>` / `CANNOT REACH <host>` ([[Standing up the endpoint]]). Without one — a facility MEP — `_connect_mep` (`:1258`) only **attaches** (reads the manager's status; an OFFLINE manager is a `failed` naming the facility as owner) and returns `needs_account` with `reused=True`, saying whether an account is needed (`account_required`) and that attaching does *not* test the identity mapping. `_shape_reject` (`:489`) then refuses the `login` shape at every entry point (`ensure_endpoint_up`, `run_shell`, `reset_session`, `login_shell`) before a `ShapeRuntime` exists.
  34: - **The provision choke point.** `_provision` (`:725`): the spend floor → bootstrap if there's no endpoint → `ensure_warm` ([[lifecycle]]) → on `"warm"`, confirm a *live worker* via `_confirm_worker` (`:593`, the canary) → `_settle_billing`. Both `ensure_endpoint_up` and `run_shell` (via `_ensure_warm_runner`, `:1936`) reach it. A non-timeout canary failure marks the runner stale (`runner_stale`, rebuilt by `_runner_for` `:570`) and keeps the failed `CanaryResult`; `_dispatch_error_suffix` (`:1837`) puts its text on the `provisioning` notice, labelling a 409 `RESOURCE_CONFLICT` as TRANSIENT (`_transient_dispatch_failure`, `:1849`).
  35: - **The terminal NO ACCOUNT ([[facility-mep]]).** `_no_account_failure` (`:1877`) matches the MEP manager's identity-mapping refusals (`_NO_ACCOUNT_MARKERS`, `:1870`); `_confirm_worker` records the verdict on `ShapeRuntime.no_account` (**sticky** — later calls return without re-submitting), and `_ensure_endpoint_up` returns a terminal `down` / `_cold_outcome` (`:1905`) a terminal `failed` whose `_no_account_notice` (`:1891`) names the identity — from the error itself (`_identity_from_error`, `:1885`) or `globus_identity_label` ([[login]]) — and says what unblocks it. Cleared by a re-bind, teardown, or a new login.
  36: - **The lock.** Serialises provision / runner-swap / stop so concurrent tool calls can't race `AppCtx`. Dispatch happens *outside* the lock, so a long command doesn't serialise everything else. `_stop_endpoint` (`:1680`) cancels the block over the login shape (AMQP) via `_release_blocks_over_login` (`:1497`; `scancel` on Slurm, `qdel` on PBS, matched by the `uep.<eid>` marker), then drops the billed shape (`_drop_compute_shape`, `:1614`) — leaving the manager online for reuse; unconfirmed ⇒ `draining` ([#24](https://github.com/ryanchard/hpc-bridge/issues/24)). On a MEP `_stop_mep` (`:1633`) is **draining-only and terminal** (no cancel channel; refuses while a task still runs), and `_teardown_endpoint` (`:1725`) is a **detach** ([[Cost control]]). The runner `close()` is non-blocking ([[runner]]) so a stop returns promptly.
  37: - **Long-task poll handles ([#21](https://github.com/ryanchard/hpc-bridge/issues/21)).** A command that outlives the sync-wait is registered in `AppCtx.tasks` (`_register_task`, `:1971`) and returned as `phase="running"`; `_poll_task` (`:2123`) reaps it via `_resolve_task` (`:1999`). A live task short-circuits the warmth [[Warmth, the canary & cold-start|canary]], blocks a same-session second dispatch (`_busy_session`, `:1949`) **and** a partition/account change (both would corrupt or cancel it), and every block-close site drains the registry (`_drain_shape_tasks`, `:560`). A pending task whose endpoint is unbound or reports offline is **ORPHANED** — `_endpoint_gone` (`:2097`) / `_orphaned_outcome` (`:2110`): a terminal `failed`, handle dropped, instead of `running` forever ([#44](https://github.com/ryanchard/hpc-bridge/issues/44); a killed block under a *live* endpoint still reads `running` — Parsl relaunches it).
  38: - **The spend floor.** `_provision` returns `"needs_confirmation"` for a billed (`compute`) shape until `confirm_spend=True` — see [[Resource shapes & the spend floor]]. Partition/account selection is threaded in via `_apply_partition` (`:761`) / `_apply_account` (`:787`) after `_VALID_PARTITION`/`_VALID_ACCOUNT` (`:757`) validate the token. `_needs_confirmation_notice` (`:808`) names the free login shape as the alternative only where one exists.
  39: - **Pilot-state observability ([#32](https://github.com/ryanchard/hpc-bridge/issues/32)).** When a billed block stays cold, `_ensure_endpoint_up` (`:826`) enriches the `provisioning` notice with the pilot's ACTUAL scheduler state — read over the login shape (AMQP) by the same `uep.<eid>` marker the release path uses (`_pilot_status_over_login`, `:1589`; `_augment_provisioning_notice`, `:1601`): `RUNNING`/queued/`HELD`, or, past a ~45 s grace (`PROVISION_GRACE_S`, clocked by `ShapeRuntime.provisioning_since`), *"no pilot → likely REJECTED"*. Otherwise a rejected/held `qsub` (bad account, missing `filesystems` directive) is indistinguishable from a normal queue wait — surfaced live on [[Aurora (PBS + bastion) bring-up|Aurora]]. Skipped on a MEP (no login shape); there, "provisioning with no canary ever recorded" means the manager reported OFFLINE, and the notice says so. A warm billed block's notice also carries `_billed_bounds_note` (`:698`) and, with no charge factor configured, says `session_spend: 0` is not a free tier.
  40: 
  41: > [!warning] "warm" means a *worker* answered — not "manager online"
  42: > `manager_online` (a cheap web query) only reflects the login-node manager. In the MEP model the first task forks the UEP and submits the block, so the manager reads online while the next command would cold-start. `_confirm_worker` submits a **canary** through the real Executor; only a returned result ⇒ warm. `CANARY_TTL_S` (`:460`) then trusts that for 45 s so an interactive burst doesn't pay the round-trip each call. See [[Warmth, the canary & cold-start]].
  43: 
  44: > [!warning] The login gate must run before the SDK `Client` is built
  45: > `_make_search_client` uses `Client(do_version_check=False)` and `app.login_required()` (non-prompting) precisely because the SDK's version check is an *authenticated* call: on a fresh install it would trigger the SDK's command-line login — a URL on stdout and `input()` on stdin, i.e. the MCP transport (found in the [#48](https://github.com/ryanchard/hpc-bridge/issues/48) review). Keep the gate first in `_connect_facility`.
  46: 
  47: > [!note] In flight (PR [#51](https://github.com/ryanchard/hpc-bridge/issues/51), open)
  48: > Two product changes ride the agentic-scenarios PR: `TRANSIENT_CONFLICT_LIMIT` (three consecutive `RESOURCE_CONFLICT` refusals ⇒ a `down` saying another session with the same identity holds the endpoint — a model sweep showed an agent retrying 7×), and `_propose_or_ask` routing a refused probe SSH through `_explain_provision_error`. On `main` the transient hint repeats and the probe path returns the raw text.
  49: 
  50: ## See also
  51: [[Two-channel architecture]] · [[Warmth, the canary & cold-start]] · [[Resource shapes & the spend floor]] · [[The MCP tools]] · [[login]] · [[facility-mep]] · [[runner]] · [[lifecycle]] · [[facility-remote]] · [[Facility catalog]] · [[Configuration]]
```
</details>


# ITEM 9

## ep:Modules/dispatch.md|2026-09-23T00:57:43Z|sha256:6c474|src/hpc_bridge/server.py#_run_shell
**episode** · note `Modules/dispatch.md` · seq 24 · commit 45547b6b · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#_run_shell` _run_shell — **body**  (note lines [8])
  ```
  was: async def _run_shell(
    app: AppCtx, command: str, session_id: str = "default", shape: str = DEFAULT_SHAPE
) -> ShellOutcome:
    session = Session(session_id, app.scratch_root)  # validates session_id before provisioning
    busy = None
    async with app.lock:  # provision + bind the runner atomically (no race with a concurrent stop)
        not_warm = await _ensure_warm_runner(app, shape)
        runner = _shape_runtime(app, shape).runner
        if not_warm is None:
            busy = _busy_session(app, shape, session_id)
    if not_warm == "needs_confirmation":  # billed shape, spend no
  ---
  now: async def _run_shell(
    app: AppCtx, command: str, session_id: str = "default", shape: str = DEFAULT_SHAPE
) -> ShellOutcome:
    if reject := _shape_reject(app, shape):
        return _shape_reject_outcome(reject)
    session = Session(session_id, app.scratch_root)  # validates session_id before provisioning
    busy = None
    async with app.lock:  # provision + bind the runner atomically (no race with a concurrent stop)
        not_warm = await _ensure_warm_runner(app, shape)
        runner = _shape_runtime(app, shape).runner
        if not_warm is None:
            busy = _busy_session(a
  ```

<details><summary>note</summary>

```
   1: # dispatch.py
   2: 
   3: > [!abstract] Role
   4: > Translates a dispatch into a structured `ShellOutcome` — and turns **any** failure into a structured `failed` result rather than raising, so a hung/broken endpoint never crashes the MCP tool or hangs the agent silently.
   5: 
   6: ## What it does
   7: 
   8: `execute(command, runner, …)` (`dispatch.py:19`) calls `runner.run()` ([[runner]]); on success it shapes a `complete` [[models|`ShellOutcome`]] via `complete_outcome` (capped stdout/stderr — [[cost]] `cap_output`). On *any* exception, `failure_outcome` maps it to a `failed` outcome with a helpful notice. Both shapers are **public and shared** with the server's submit/poll path (`_run_shell` / `poll_task`), so the completion/failure mapping lives in one place ([#21](https://github.com/ryanchard/hpc-bridge/issues/21)):
   9: 
  10: | Failure | exit | notice |
  11: |---|---|---|
  12: | `TimeoutError` | 124 | "timed out — run ensure_endpoint_up and retry, or move to a batch job" |
  13: | `MaxResultSizeExceeded` | 1 | "exceeded the 10 MB result limit — redirect to a file" |
  14: | `TaskExecutionFailed` | 1 | "the remote task failed to execute" |
  15: | other | 1 | "Dispatch error: \<type\>" |
  16: 
  17: > [!note] Pure layer
  18: > SDK exceptions are matched by **class name**, not by importing `globus_compute_sdk` — keeping this translation layer free of the heavy integration dependency.
  19: 
  20: ## See also
  21: [[models]] · [[runner]] · [[server]] · [[cost]]
```
</details>


# ITEM 10

## ep:Modules/facility-remote.md|2026-09-23T00:58:22Z|sha256:0f07e|src/hpc_bridge/server.py#_control_settings
**episode** · note `Modules/facility-remote.md` · seq 33 · commit c076dc74 · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#_control_settings` _control_settings — **body**  (note lines [27])
  ```
  was: def _control_settings() -> tuple[str | None, int]:
    """ControlMaster socket dir + persist for SSH multiplexing — one authentication for the whole
    bootstrap+discovery. Shared by _slurm_facility and the discovery probe so they reuse ONE master
    (same user@host ⇒ same %C socket). HPC_BRIDGE_SSH_CONTROL_PERSIST=0 disables it (control_dir=None)."""
    try:
        persist = int((os.environ.get("HPC_BRIDGE_SSH_CONTROL_PERSIST", "60") or "60").strip())
    except ValueError:
        persist = 60
    if persist <= 0:
        return None, 60
    from .state import _state_dir

    cd = str(_s
  ---
  now: def _control_settings() -> tuple[str | None, int]:
    """ControlMaster socket dir + persist for SSH multiplexing — one authentication for the whole
    bootstrap+discovery. Shared by _slurm_facility and the discovery probe so they reuse ONE master
    (same user@host ⇒ same %C socket). HPC_BRIDGE_SSH_CONTROL_PERSIST=0 disables it (control_dir=None)."""
    try:
        persist = int((os.environ.get("HPC_BRIDGE_SSH_CONTROL_PERSIST", "60") or "60").strip())
    except ValueError:
        persist = 60
    if persist <= 0:
        return None, 60
    from .state import _state_dir

    cd = _short
  ```

<details><summary>note</summary>

```
   1: # facility-remote.py — `facility/remote.py`
   2: 
   3: > [!abstract] Role
   4: > Everything machine-specific for a remote **Slurm or PBS** cluster, behind one [[facility-base|Facility]]: the SSH transport, the per-facility `MachineProfile`, the `globus-compute-endpoint` CLI driver, and `SlurmFacility` (bootstrap / provision / teardown / config template). Despite the name, `SlurmFacility` drives **both** schedulers — the template split, not the class, is scheduler-specific.
   5: 
   6: ## The pieces
   7: 
   8: - **SSH transport** — `SshTarget` (`:42`) + `ssh_exec()` (`:112`): `BatchMode` (never prompts), reaps the child on timeout/cancel (no process/FD leak). **Identity defers to `~/.ssh/config`** — `user`/`key_path` are optional; absent ⇒ a bare `host` so OpenSSH resolves `User`/`IdentityFile` **and `ProxyJump`** itself (`-i`/`IdentitiesOnly` only with an explicit key). That `ProxyJump` deferral is why a **bastion two-hop** (ALCF Aurora: `bastion.alcf.anl.gov` → login node) is transparent — no new code ([[Aurora (PBS + bastion) bring-up]]). Also drives the un-indexed [[discovery]] probe (`ssh_exec` on a bare target, pre-endpoint). The control channel of [[Two-channel architecture]]; see *Persistent SSH* below.
   9: - **Per-facility data** — `MachineProfile` (`:182`): host, `env_setup` (module + venv), `interface`, partition, account, scratch, plus **`scheduler`** (`slurm`/`pbs`) and **`cpus_per_node`** (PBS) — supplied by the [[Facility catalog|catalog]] (`profile_from_catalog_entry`, `:207`, which derives `endpoint_name` = `hpc-bridge-<id>` when a seed omits it), no longer hardcoded per machine.
  10: - **gce driver** — `RemoteEndpointCLI` (`:270`): runs `globus-compute-endpoint` over SSH via `_gce` (`:282`); also `login_exec` (`:286`, backs the `login_shell` tool), `seed_storage_db` (`:357`, [[Credential seeding]]), `configure`/`start`/`stop`, `clean_uep_pidfiles` (`:409`, removes stale per-UEP `daemon.pid` files scoped to the endpoint UUID so a rebuilt worker doesn't hit "Another instance is running" → exit 73 — [#37](https://github.com/ryanchard/hpc-bridge/issues/37); `provision` calls it before a restart), `cancel_blocks` (`:430`, scheduler-aware — `scancel`, or `qdel` via `_cancel_blocks_pbs` (`:466`)), and `close` (`:527`, drops the ControlMaster).
  11: - **Orchestration** — `SlurmFacility` (`:602`): `bootstrap` (`:682`), `provision` (`:723`), `config_template` (`:625`, picks `_SLURM_TEMPLATE` (`:513`) / `_PBS_TEMPLATE` (`:554`) by `profile.scheduler` — [[MEP & templated endpoints]]), `teardown` (`:757`), `manager_online` (`:775`, web), `find_online_endpoint` (`:782`, web reuse).
  12: 
  13: ## How a stand-up flows
  14: 
  15: `bootstrap` (`:682`) is the entry point, and it is **reuse-or-SSH**: it first asks the Globus *web* service whether we already own an online endpoint (`find_online_endpoint`, `:782`) → reuse over AMQP, **zero SSH**. Only if none is online does it seed credentials (when needed) and call `provision` (`:723`): `configure` if absent → write the engine-free manager `config.yaml` + the scheduler's UEP template → `start` (detached) → capture & **pin** the login node. See [[Standing up the endpoint]].
  16: 
  17: > [!warning] Login-node pinning
  18: > The manager lives on ONE login node, but HPC SSH aliases round-robin. `start` (`:371`) captures the FQDN *in the same SSH connection* that launches the daemon (a separate probe could resolve a different node), records it via [[state]]'s `LoginNodeStore`, and the CLI `rebind`s (`:491`) straight there next session. **`_routable_pin` (`:164`) first drops a FQDN that isn't reachable from the client** — an internal suffix (`.local`/`.internal`), a single label, or a **management-plane** name (`hostmgmt`/`cm`/`mgmt`/`ipmi`/`bmc` labels, e.g. Aurora's `aurora-uan-0009.hostmgmt.cm.aurora.alcf.anl.gov`) — falling back to the alias, so a non-routable pin can't break teardown/reconnect ([#33](https://github.com/ryanchard/hpc-bridge/pull/33)).
  19: 
  20: > [!warning] PBS cancel reads bare `qstat -f`, never `-u`
  21: > Slurm block-release matches `squeue -u`, but PBS Pro's `-u` filter suppresses full-format output entirely — so `_cancel_blocks_pbs` (`:434`) uses bare `qstat -f` (unwrapping its 80-col line continuations) scoped by the endpoint-unique `uep.<eid>` marker → `qdel`. A `-u` filter would silently no-op and let the block burn to walltime (caught in live Polaris validation, [#28](https://github.com/ryanchard/hpc-bridge/issues/28)). The marker scoping means it never touches another endpoint's jobs, same as the Slurm path.
  22: 
  23: > [!warning] `gce list` parsing is fail-loud
  24: > `status`/`endpoint_id` parse `gce list`'s ASCII pipe-table via `_parsed_rows` (`:305`); a gce version/format change **raises** rather than being misread as "no endpoints" (which would trigger a wrong re-provision). See [#8](https://github.com/ryanchard/hpc-bridge/issues/8).
  25: 
  26: > [!note] Persistent SSH (ControlMaster) — authenticate once
  27: > `SshTarget.argv` (`:61`) appends `ControlMaster=auto` + a `%C`-keyed `ControlPath` + `ControlPersist` (configured by `_control_settings`, [[server]]) when a socket dir is set, so all of a facility's SSH — the ~10-call cold bootstrap *and* the [[discovery]] probe — rides **one authenticated connection**. On a key facility the master opens non-interactively; on an MFA facility the user pre-opens it once (one Duo) and the server's `BatchMode` calls multiplex over it. `close` (`:495`) tears it down (`ssh -O exit`); `ControlPersist` self-reaps regardless. *(Honest nuance: the post-`start` `rebind` to the pinned node means a cold bootstrap ends with two masters — alias + node — so 2 auths, not 1; still decisive vs ~10.)*
  28: 
  29: > [!note] Endpoint reuse (zero-SSH reconnect)
  30: > `find_online_endpoint` reuse is the keystone that lets a reconnect session avoid SSH **entirely** — one of two MFA mitigations (the other is persistent SSH, above) ([#3](https://github.com/ryanchard/hpc-bridge/issues/3)). It gates on `manager_online` **alone — no liveness probe** (a probe can't tell a dead ghost from a cold-starting fresh worker); a dead "online" ghost is instead recovered downstream, where the robust [[Warmth, the canary & cold-start|canary]] maps its shut-down Executor to `provisioning` ([#37](https://github.com/ryanchard/hpc-bridge/issues/37)). See [[Two-channel architecture]] and [[Discovery today]].
  31: 
  32: ## See also
  33: [[Standing up the endpoint]] · [[Credential seeding]] · [[MEP & templated endpoints]] · [[facility-base]] · [[state]] · [[credentials]]
```
</details>


# ITEM 11

## ep:Concepts/Warmth, the canary & cold-start.md|2026-09-23T01:00:34Z|sha256:1a1c2|src/hpc_bridge/server.py#ShapeRuntime
**episode** · note `Concepts/Warmth, the canary & cold-start.md` · seq 41 · commit 923183c1 · state broken

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#ShapeRuntime` ShapeRuntime.last_canary — **anchor-missing** symbol_not_found (note lines [16, 20])

<details><summary>note</summary>

```
   1: # Warmth, the canary & cold-start
   2: 
   3: > [!abstract] In one line
   4: > "Up" means a **worker answered**, not that the manager is online — so before trusting an endpoint we submit a tiny **canary** task through the real Executor; a returned result ⇒ warm, a timeout ⇒ still cold (and the submit itself kicks the block).
   5: 
   6: ## The cold-start gap
   7: 
   8: `manager_online` is a cheap Globus *web* query that only reflects the **login-node manager**. But in the [[MEP & templated endpoints|MEP model]] the first task forks the UEP and submits the scheduler block, so the manager reads "online" while the next command would still **cold-start** (no worker yet). Trusting `manager_online` makes `run_shell` dispatch into a 124 timeout.
   9: 
  10: ## The canary
  11: 
  12: `_confirm_worker` ([[server]], `server.py:593`) submits a trivial `ShellFunction` through the *same* long-lived Executor real work uses ([[runner]], `GlobusRunner.canary`). The canary command echoes a sentinel plus the worker's host, Python, and dill versions:
  13: 
  14: - **returned result** ⇒ a worker is truly live ⇒ `warm`.
  15: - **timeout** (`CANARY_TIMEOUT_S = 8 s`, `server.py:463`) ⇒ still `provisioning` — and the submit has *kicked* the cold block.
  16: - **submit/dispatch failure** — e.g. a reused endpoint whose Executor is shut down ⇒ **not-warm** → `provisioning`, never a propagating crash. This is the [#37](https://github.com/ryanchard/hpc-bridge/issues/37) mechanism that lets a stale-"online" reused ghost degrade to `provisioning` (recover by teardown) instead of dead-ending in `RuntimeError: Executor is shutdown`. A **non-timeout** failure additionally means the dispatch path itself broke (the web service refused the submit — a config the endpoint's schema rejects, a bad partition) and the SDK Executor has shut *itself* down, so `_confirm_worker` marks the runner stale (rebuilt on the next call) and keeps the failed `CanaryResult` as `last_canary`: its text (the API error's `.message`, kept whole by [[runner]] `dispatch_error_text`) rides the `provisioning` notice as a `— last dispatch failed: …` suffix (`_dispatch_error_suffix`), so the cause is visible rather than buried under "allocating nodes…". A `RESOURCE_CONFLICT` (the web service's 409 "already in use … concurrent requests", seen when two submits land within ~2 s) is labelled **TRANSIENT** — wait ~10 s and call again. *(PR [#51](https://github.com/ryanchard/hpc-bridge/issues/51), open, caps that at `TRANSIENT_CONFLICT_LIMIT` = 3 in a row → a `down` saying another session with the same identity holds the endpoint.)*
  17: 
  18: A successful canary is trusted for `CANARY_TTL_S = 45 s` (`server.py:460`) so an interactive burst doesn't pay the round-trip every call. (Safe: an idle block needs ≥ `max_idletime`, default 600 s, of silence to release, so a worker seen < 45 s ago can't have vanished.)
  19: 
  20: **Terminal failures the canary surfaces.** On a facility MEP ([[facility-mep]]) the canary is also where the identity mapping is tested. The manager's no-account notices (`_NO_ACCOUNT_MARKERS`, [[server]]) turn `provisioning` into a terminal `down` (`ensure_endpoint_up`) / `failed` (a cold `run_shell`) that names the refused Globus identity, and the verdict is **sticky** (`ShapeRuntime.no_account`: `_confirm_worker` returns without re-submitting; cleared by a re-bind, teardown, or a new login). And because a MEP's `manager_online` degrades to `True` on a status-API error, "provisioning with **no canary ever recorded**" there means the manager itself reported OFFLINE — a facility outage, not a queue wait — and the notice says so instead of "allocating nodes…".
  21: 
  22: A **running task is itself liveness.** While a long poll-handle task ([#21](https://github.com/ryanchard/hpc-bridge/issues/21)) is executing on a shape, `_confirm_worker` returns `warm` **without** a canary: the worker is demonstrably running our work, and a canary would only queue behind the sole worker and — on timeout — wrongly flip us to "not warm", banking the [[Cost control|spend clock]] while the block is still burning.
  23: 
  24: > [!warning] dill skew is the real failure mode
  25: > The canary reports the worker's dill version; if it differs from ours, function (de)serialization breaks. `_worker_notice` surfaces that as the warm descriptor's warning — it's the genuine compatibility hazard behind "the worker is up but tasks fail."
  26: 
  27: This is what makes `ensure_endpoint_up`'s "is it warm?" honest and keeps `run_shell` from dispatching into a hang ([[dispatch]] turns a real timeout into a structured outcome).
  28: 
  29: ## See also
  30: [[server]] · [[runner]] · [[lifecycle]] · [[MEP & templated endpoints]] · [[facility-mep]] · [[Cost control]]
```
</details>


# ITEM 12

## ep:Reference/Plugin review 2026-09-05.md|2026-09-23T01:07:17Z|sha256:47235|src/hpc_bridge/scheduler_ops.py#_release_blocks_over_login
**episode** · note `Reference/Plugin review 2026-09-05.md` · seq 107 · commit adca645d · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/scheduler_ops.py#_release_blocks_over_login` _release_blocks_over_login — **signature**  (note lines [24])
  ```
  was: async def _release_blocks_over_login(app: AppCtx, eid: str, run_login: LoginRunner) -> tuple[bool, str]:
    """Cancel this endpoint's scheduler block(s) by running the scheduler's cancel (scancel/qdel)
    on the **login shape (AMQP)** — never SSH. That's the whole point of the login-node endpoint:
    talk to the cluster over Compute, not a fresh SSH. Matches blocks precisely by the UEP StdOut
    marker (`uep.<eid>`) so it never touches another endpoint's jobs.

    A cold login worker can't dispatch on the first try — it returns cold_start ("allocating
    nodes…"), not `complete`. But tha
  ---
  now: async def _release_blocks_over_login(
    app: AppCtx, eid: str, run_login: LoginRunner, *, expect_block: bool = False
) -> tuple[bool, str]:
    """Cancel this endpoint's scheduler block(s) by running the scheduler's cancel (scancel/qdel)
    on the **login shape (AMQP)** — never SSH. That's the whole point of the login-node endpoint:
    talk to the cluster over Compute, not a fresh SSH. Matches blocks precisely by the UEP StdOut
    marker (`uep.<eid>`) so it never touches another endpoint's jobs.

    A cold login worker can't dispatch on the first try — it returns cold_start ("allocating

  ```

<details><summary>note</summary>

```
   …
  20: ### 1. HIGH — `teardown_endpoint` reports `down`, "gce-stopped" and "token copy removed" without measuring any of them; BYO MFA facilities are never gated
  21: 
  22: **Where.** `src/hpc_bridge/facility/remote.py:519-522` (`stop` discards the SSH rc), `:573-575` (`wipe_storage_db` drops the result), `:984-987` (`wiped = True` unconditionally), `:988-989` (`store.remove` regardless of outcome), `:993` (`ssh_closed` derived from `control_dir is not None`, not from `close()`); `src/hpc_bridge/server.py:681-703` (`_finish_teardown` answers `down` and clears state even when `teardown()` raised); `server.py:706-717` (`_teardown_preauth_gate` fires only when `auth_method == "mfa-otp"`); `src/hpc_bridge/binding.py:243-284` (`_entry_from_details` never sets `auth_method`; `FacilityDetails` has no such field; `connect.py:378-381` records nothing on `NeedsPreauth`). Only `catalog/seed/sdsc-expanse.yaml:15` carries `mfa-otp` today.
  23: 
  24: **Failing sequence.** BYO MFA facility (`connect_facility(details=…)` after the `needs_preauth` → `complete_preauth` handoff). Hours later the user's `ssh -fN` master (`ControlPersist=1h`, `remote.py:124`) is gone. `teardown_endpoint` → gate returns `None` (`auth_method` is the CatalogEntry default `ssh-key`) → `_release_blocks_over_login` → `teardown()`: `stop()` rc=255 under `BatchMode` ignored; `cancel_blocks` → `[]`; `delete()` → `False`; `wipe_storage_db()` rc dropped, then `wiped = True`; `store.remove` deletes the record carrying `seeded_credentials`; `ssh_closed = True`. `_finish_teardown` reports `status="down"`, "manager gce-stopped, but DELETE FAILED … the Globus token copy hpc-bridge placed on the login node removed; the shared SSH connection … was closed", and `_drop_all_shapes`. Reality: manager running, `storage.db` still on the login node, pin and seeded-flag gone — so no later teardown can ever wipe the bearer token (`_seeded_by_us`, `remote.py:916-924`, reads that record). The trailing "It will NOT be reused" is false too: the registration survives and the next `connect_facility`'s `find_online_endpoint` re-adopts it. Reproduced hermetically with every SSH op returning rc=255. `tests/test_security_review.py:431-501` and `tests/test_server.py:678-720` only exercise fakes where every op succeeds or `auth_method = "mfa-otp"`.
  25: 
  26: **Fix.** Make `stop()`/`wipe_storage_db()` return their rc and have `teardown()` report `stopped`/`credentials_wiped` from them; remove the `LoginNodeStore` record only when `deleted` is `True`; in `_finish_teardown` return `status="up"` (or a new `teardown_failed`) and keep state when `stopped` is `False` or `teardown()` raised. Gate on evidence, not the curated flag: run `_teardown_preauth_gate` whenever the target has a `control_dir` and no master is alive, or record `auth_method="mfa-otp"` on the session entry when the probe raised `NeedsPreauth`. Add the rc=255 fake-CLI test.
  27: 
  28: ### 2. HIGH — `main` is CI-red and the "hermetic" unit tier reads the live registry and writes the developer's real cache
```
</details>


# ITEM 13

## ep:Modules/discovery.md|2026-09-23T00:57:14Z|sha256:029d6|src/hpc_bridge/catalog/entry.py#CatalogEntry
**episode** · note `Modules/discovery.md` · seq 24 · commit 45547b6b · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/catalog/entry.py#CatalogEntry` CatalogEntry.ssh_host — **body**  (note lines [8, 20])
  ```
  was: ssh_host: str
  ---
  now: ssh_host: str | None = None
  ```

<details><summary>note</summary>

```
   1: # discovery.py
   2: 
   3: > [!abstract] Role
   4: > The raw-SSH **login-node probe** for an **un-indexed** facility: one batched command → a *proposed* [[models|FacilityDetails]] draft the user confirms. The cache-miss path of the [[Facility catalog|catalog]] — the pre-endpoint discovery channel the [[Globus index discovery channel]] reserved, now wired.
   5: 
   6: ## What it does
   7: 
   8: `discover_facility_details(target)` (`discovery.py:50`) runs **one** batched `ssh_exec` over a bare [[facility-remote|SshTarget]] — just an `ssh_host` plus `~/.ssh/config` credentials, with **no endpoint and no catalog entry needed yet** — then `parse_probe()` (`:63`) turns the output into a `(FacilityDetails, notes)` pair. `notes` names the low-confidence fields the agent must confirm with the user — `interface` above all.
   9: 
  10: ## How it works
  11: 
  12: - **One probe, framed.** `_PROBE` is a single compound bash script (one SSH round-trip ⇒ MFA-once-friendly) emitting `KEY=value` lines between `HPCB_PROBE_BEGIN`/`END` sentinels (so a login banner can't pollute the parse); multi-valued facts (`PART`/`QUEUE`/`NIC`) repeat their key. `_collect()` reads only the framed block.
  13: - **Scheduler detection.** The probe checks `sbatch` (⇒ `scheduler="slurm"`) then `qsub` (⇒ `"pbs"`); neither ⇒ default `slurm` + a flag. This picks the queue source (`sinfo` vs `qstat -Q`) and, downstream, the [[facility-remote|scheduler template]].
  14: - **Deterministic per-field proposers** (never model inference): `_interface()` (`:181`) picks the worker NIC from `ip -o -4 addr`, ranking the dedicated compute fabric (`_FAST_NIC_ORDER` — `hsn`/`ipogif`/`ib`/`hsi` over a `bond` mgmt NIC), else the single candidate — *always* flagged; `_default_partition()` (`:159`, Slurm `sinfo`) / `_default_queue()` (`:172`, PBS `qstat -Q`) prefer a cheap `debug`/`shared`/`prod`; scratch from `$SCRATCH`/`$WORK`/`$HOME` (templated to `{user}`); `_env_setup()` returns an activate line if gce is already installed, else the idempotent **uv create-venv + install** one-liner (`_UV_ENV_SETUP`) when `uv` is present; `_allocation()` detects `mybalance`/`xdusage`.
  15: - **`{user}` templating** comes from the probe's own `whoami`, so the draft is per-user with no env var.
  16: 
  17: Reached from `connect_facility`'s index-miss path: `_propose_or_ask` ([[server]] `:871`) builds the bare target and returns `phase="proposed_facility_details"` (or `needs_preauth` when the host needs an interactive login).
  18: 
  19: > [!note] The full resolution ladder
  20: > This probe is the **last rung**. `connect_facility` walks session → `facilities.json` (local cache) → catalog → probe, first hit wins — the agent never reads the cache itself; it's resolved server-side inside the one call. See the interactive diagram: **[the resolution ladder](../assets/discovery-resolution-ladder.html)** (open in a browser), which also maps where the agent can *deviate* — bypassing `connect_facility`, an inconsistent `ssh_host` key, or a fabricated `details=`.
  21: 
  22: > [!warning] Propose, don't invent
  23: > Discovery *proposes* discovered facts for the user to confirm; it must not silently commit. A wrong `interface`/`env_setup` is caught by the [[Warmth, the canary & cold-start|canary]] (the worker never registers), so the draft is **checkable, not trusted** — elicit → propose → confirm → validate.
  24: 
  25: ## See also
  26: [[Globus index discovery channel]] · [[server]] · [[models]] · [[facility-remote]] · [[Discovery channel model]] · [[Facility catalog]]
```
</details>


# ITEM 14

## ep:Modules/state.md|2026-09-23T01:00:59Z|sha256:ac703|src/hpc_bridge/server.py#_short_control_dir
**episode** · note `Modules/state.md` · seq 42 · commit bb06af3f · state broken

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#_short_control_dir` _short_control_dir — **anchor-missing** symbol_not_found (note lines [8])

<details><summary>note</summary>

```
   1: # state.py
   2: 
   3: > [!abstract] Role
   4: > Durable local state under `~/.hpc-bridge/` (relocatable via `HPC_BRIDGE_STATE_DIR`): the [[Standing up the endpoint|login-node pin]] and the **local-discovery cache** of confirmed BYO facility configs.
   5: 
   6: ## What it does
   7: 
   8: - **`_state_dir()`** (`state.py:18`) — the state root: `HPC_BRIDGE_STATE_DIR` or `~/.hpc-bridge`. The env override lets tests point it at a tmp dir so they never touch real state. It also roots the ControlMaster sockets (`<state>/cm`) — but [[server]]'s `_short_control_dir` swaps in `~/.hpc-bridge/cm` or `/tmp/hpcb-cm-<uid>` when that path would push the expanded `ControlPath` past the Unix socket cap (`ControlPath too long`, found on the stranger's walk with a deep temp dir).
   9: - **`EndpointRecord`** (`:26`) — `endpoint_id`, `login_host` (resolved FQDN), `alias` (the round-robin SSH alias), `user`, `key_path`, `name`, `provisioned_at`.
  10: - **`LoginNodeStore`** (`:40`) — JSON at `~/.hpc-bridge/endpoints.json`, keyed by `(alias, name)`. `put`/`get`/`remove`/`all` — the login-node pin.
  11: - **`FacilityStore`** (`:79`) — JSON at `~/.hpc-bridge/facilities.json`, keyed by **`ssh_host`**. Caches a confirmed BYO `FacilityDetails` dict (`get`/`put`/`remove`, `:106`–`:115`) so a later session **reconnects from the cache with no SSH probe** — the local half of discovery: [[server]]'s `connect_facility` resolves a known `ssh_host` here before ever probing. See [[Discovery today]].
  12: 
  13: > [!warning] Written `0600` from creation
  14: > Both stores reference a credentialed host, so `_save` opens with `0o600` and `chmod`s — the file never exists world-readable, even briefly.
  15: 
  16: Used by [[facility-remote]]: `bootstrap` records the login pin after `start`; `_slurm_facility` ([[server]]) reads it — at startup *and* on every `connect_facility` bind — and `rebind`s the CLI to that node when `_routable_pin` accepts it. **Nothing removes a pin today**: `LoginNodeStore.remove` exists but no caller uses it (`teardown` leaves the record), so a routable-but-dead pin fails fast under `BatchMode` and the reset is to delete `~/.hpc-bridge/endpoints.json` by hand. `connect_facility` reads/writes `FacilityStore` — a confirmed session facility is cached, and a known `ssh_host` then resolves from it with zero SSH — but only **after** the registry misses ([[Facility catalog]] precedence). The registry's own fetched-entry cache lives elsewhere (`<CLAUDE_PLUGIN_DATA or ~/.hpc-bridge>/catalog-cache/`, [[Facility catalog]]).
  17: 
  18: > [!note] Superseded: "teardown removes the pin"
  19: > An earlier version of this note said `teardown` removes the pin once the daemon is gone. It doesn't — see above. (Reported in the 2026-09-03 vault audit as a code gap, not fixed in the docs by pretending otherwise.)
  20: 
  21: ## See also
  22: [[Standing up the endpoint]] · [[facility-remote]] · [[Discovery today]] · [[Facility catalog]] · [[Two-channel architecture]] · [[Configuration]]
  23: 
  24: > [!note] Decided 2026-09-03 — the facility cache is PROVEN, not accepted; dead pins are dropped
  25: > `FacilityStore` is written only when the login shape's canary has answered on that config (`_commit_proven_facility`, via `AppCtx.pending_facility_cache`) — the canary is what exercises the discovered network interface, the probe's riskiest guess; a config merely supplied, or merely accepted by the bootstrap, is never remembered. And a login-node pin whose host is UNREACHABLE (`CANNOT REACH`) is dropped by `_drop_dead_pin` so the next connect resolves the canonical host again; a refused login keeps the pin. Before this, pins were permanent (`LoginNodeStore.remove` had no caller).
```
</details>


# ITEM 15

## ep:Planned/Endpoint reuse and MEP integration.md|2026-09-23T01:00:39Z|sha256:eb6ce|src/hpc_bridge/server.py#_confirm_worker
**episode** · note `Planned/Endpoint reuse and MEP integration.md` · seq 47 · commit 524c3dc7 · state broken

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#_confirm_worker` _confirm_worker — **anchor-missing** symbol_not_found (note lines [101])

<details><summary>note</summary>

```
   1: # Endpoint reuse and MEP integration
   2: 
   3: > [!abstract] In one line
   4: > The zero-SSH ladder: first **surface the reuse hpc-bridge already does silently** for endpoints it stood up, then **consume facility-run multi-user MEPs** so the facility's identity mapping replaces our SSH bootstrap outright — shrinking SSH from "every cold start" toward "never." **Phase 1 (reuse our own) SHIPPED ([#20](https://github.com/ryanchard/hpc-bridge/issues/20)); Phase 2 M1 (facility MEPs) SHIPPED ([#41](https://github.com/ryanchard/hpc-bridge/issues/41), 2026-09-03)** — the V1-gating objective (user, 2026-07-20), validated live on globus1. The implementation is ground truth in [[facility-mep]] and [[server]]; this note keeps the design and the live record. M2 (the consent flow — the graceful browser-auth story for consent-gated facilities) is deferred to V1.x ([[V1 release]]).
   5: 
   6: ## The reuse ladder
   7: 
   8: Three ways to reach a warm compute channel, best-first — each removes more SSH:
   9: 
  10: | Tier | Mechanism | SSH cost | Status |
  11: |---|---|---|---|
  12: | 1. **Facility MEP** | submit a UEP config to a facility's multi-user (identity-mapped) manager UUID | **none, ever** | **Phase 2 M1 — SHIPPED** ([#41](https://github.com/ryanchard/hpc-bridge/issues/41)): `MEPFacility`, catalog-driven; globus1 live |
  13: | 2. **Our online endpoint** | reattach to an already-running `hpc-bridge-<facility>` by name | none after the first bootstrap | **Phase 1 — SHIPPED** ([#20](https://github.com/ryanchard/hpc-bridge/issues/20)): signal surfaced + inter-agent chain test |
  14: | 3. **SSH bootstrap** | SSH in once, start our own personal manager | one bootstrap (~2 auths) | built — the current default |
  15: 
  16: ## Two senses of "MEP" — don't conflate them
  17: 
  18: [[MEP & templated endpoints]]: hpc-bridge's endpoint *is already* a Globus v4 MEP — but in **personal / single-user mode** (`configure --multi-user false`, `endpoint.py:58`), where "multi-user" names only the **manager + templated-UEP** architecture, not identity mapping. We own that manager; it serves one user.
  19: 
  20: A **facility MEP** (Phase 2) is the *other* sense: a manager the **facility** runs in **true multi-user mode with identity mapping** — one daemon serving many users, forking an identity-mapped UEP per authenticated Globus identity. **That identity mapping is precisely what replaces our SSH bootstrap:** SSH exists today only to authenticate-as-the-user and start their personal manager; a facility MEP already runs the manager and maps our Globus identity to a local account over AMQP, so no SSH is needed. Tier 1 is not "reuse our endpoint" — it's "borrow the facility's."
  21: 
  22: ## Phase 1 — reuse hpc-bridge's own endpoints ✅ SHIPPED ([#20](https://github.com/ryanchard/hpc-bridge/issues/20), PR #26)
  23: 
  24: **The detection already existed and works cross-session.** `bootstrap()` (`facility/remote.py:544`) asks Globus, *before any SSH*, whether we already own an online endpoint by the stable name `hpc-bridge-<facility>`:
  25: 
  26: ```python
  27: reused = await self.find_online_endpoint(self.profile.endpoint_name)   # remote.py:559 / :643
  28: if reused is not None:
  29:     return EndpointHandle(endpoint_id=reused, ...)                      # zero SSH, over AMQP
  30: ```
  31: 
  32: Because the name is stable and the manager persists on the cluster, a **fresh server process reconnects to a prior session's endpoint with zero SSH** — the SSH-once story is real *today* ([[Standing up the endpoint]]).
  33: 
  34: **The gap was the signal, not the logic — now closed.** The reuse fact was computed into `reused` and then dropped (`EndpointHandle` carried no flag), so the connect result never learned it happened. #20 threaded it up: `EndpointHandle.reused` (set at `bootstrap()` `:561` and `provision()`'s `running` case `:593`, false on a fresh `start`) → `EndpointState.reused` → `ConnectFacilityResult.reused` + a "zero-SSH reconnect" notice. The agent and user can now tell "reattached, free" from "freshly bootstrapped."
  35: 
  36: **Verified two ways** (both scenarios green): `endpoint_reuse` (intra-agent — one session, two connects) live, and `endpoint_reuse_chain` (inter-agent — two agent sessions across an MCP-server restart, the true cross-session case) via re-grade of the real trace. The harness gained a `PHASES` chain primitive to run the latter (see [[Agentic testing - Plan B (runtime sandbox)]]).
  37: 
  38: > [!note] Resolved ([#37](https://github.com/ryanchard/hpc-bridge/issues/37) / [PR #38](https://github.com/ryanchard/hpc-bridge/pull/38)): stale-online reuse
  39: > Reuse **deliberately gates on `manager_online` alone — no liveness probe**: a probe can't distinguish a dead ghost from a cold-starting fresh worker, so a canary-gate *on reuse* false-rejects a healthy fresh endpoint (it was tried, then removed). A genuinely dead "online" ghost is instead handled gracefully **downstream** — the robust [[Warmth, the canary & cold-start|canary]] maps its shut-down Executor to not-warm → `provisioning`, which the agent recovers via `teardown_endpoint` + reconnect. And `provision` clears stale per-UEP `daemon.pid` files at start (the exit-73 fix). Re-bootstrap-on-stale was **rejected** — a compute-first re-bootstrap can't tell a ghost from a cold start.
  40: 
  41: ## Phase 2 — consume facility MEPs (the V1 objective)
  42: 
  43: **This is the V1 gate** (2026-07-20): a working zero-SSH MEP path before publishing V1. It is *also* the graceful-auth story — a facility MEP authorizes us by a **Globus consent (a browser OAuth)**, the same loopback + paste-back pattern the [Cloudflare MCP](https://developers.cloudflare.com/agent-setup/) uses (`authenticate` → auth URL → approve in browser → return to session). There is no SSH and no Duo to hand off. The two Globus-SDK unknowns that used to size this are now **verified against `globus_compute_sdk` 4.13.0** (inline below).
  44: 
  45: > [!success] M1 target acquired — `globus-cluster-mep` is live on globus1 (2026-08-18)
  46: > The globus-cluster admin agent stood up a true multi-user, identity-mapped MEP and verified it end-to-end (dispatch → mapped to `glabs` → Slurm job on `main`). **UUID `da3df250-4013-4d69-942c-eef1568f860c`** → the `compute_mep_uuid` for a globus1 catalog entry. Full spec + gotchas: [[globus-cluster-mep-testbed]] (memory) · cluster vault Reference/08c + D-034. Three findings shape M1:
  47: > 1. **Consent-free here.** The Bearer token flowed straight through to submission validation — no consent-required 401. So **globus1 cannot exercise M2's `needs_consent` flow**; on this facility **M1 alone is the complete zero-SSH path**. M2 still stands for facilities that *do* gate on consent — it just needs a different testbed to validate.
  48: > 2. **The login shape (`compute:false` / `LocalProvider`) is REJECTED by the MEP schema.** Forked user endpoints run in `system.slice` with no memory cgroup, so an unbounded LocalProvider task on globus1 (which is *also* the Slurm controller + NFS server) is refused outright — not silently rerouted. ⟹ **`MEPFacility` is compute-only**: no free login-node exec; map any "login" op to a warm Slurm block (`init_blocks: 1` + short walltime keeps it warm for `max_idletime`=600 s, so only the first call pays the queue). This **reinforces** the draining-only stop below — one shape, one channel.
  49: > 3. **Version pin is the client's job.** Endpoint + workers must match; theirs is `globus-compute-endpoint==4.15.0`. The catalog entry's `env_setup` → `worker_init` must install it **unconditionally** — a `command -v … || install` guard silently keeps a wrong-version venv → cryptic `process_worker_pool.py: -P/--port` job failures. Account is **not required** (`AccountingStorageEnforce=none`); pass `""` and it's stripped.
  50: 
  51: > [!note] Superseded by M1 (2026-08/09) — the pre-build analysis below is kept for the record
  52: > Everything from here to the milestone table was written *before* M1. What it proposed is now built: `_unsupported_entry_reason` no longer rejects a `compute_mep_uuid` entry (it only refuses one that also carries an `allocation` block), `_facility_from_entry` dispatches on `compute_mep_uuid` first, and the `Facility` sketch below became [[facility-mep]] as described. Point 3 (consent) is M2, still deferred; point 4 (a clear failure on an unmapped identity) is the terminal NO ACCOUNT recorded at the end of this note.
  53: 
  54: **The dispatch half is nearly built.** A Globus Compute run is already `Executor(endpoint_id, user_endpoint_config)` (`runner.py:96`) — literally what a facility MEP consumes — and the `HPC_BRIDGE_ENDPOINT_ID=<uuid>` BYO hatch (`server.py:308` `_env_endpoint_id`) already dispatches to a foreign UUID with **zero provisioning**. What's missing is everything around *choosing* and *configuring* that UUID as a first-class, discovered path.
  55: 
  56: **The information we'd need to gather** (the open question the user flagged — settle this before building):
  57: 1. **The MEP UUID, per facility** — the catalog field **already exists**: `CatalogEntry.compute_mep_uuid` (`catalog/entry.py:73`, UUID-validated). Today `_unsupported_entry_reason` (`server.py:171`) *rejects* such an entry (*"catalog-driven MEP dispatch is not wired yet — use HPC_BRIDGE_ENDPOINT_ID"*); wiring Phase 2 = replacing that reject with a MEP branch. Discovery of the UUID (a facility that *publishes* a MEP) layers on [[Discovery channel model]] / [[Globus index discovery channel]] / the ACCESS survey ([#7](https://github.com/ryanchard/hpc-bridge/issues/7)). *(2026-09-03: which facilities actually publish one is now surveyed — [[MEP facilities survey]].)*
  58: 2. **The allowed `user_endpoint_config`** — the facility owns the `user_config_template.yaml.j2` + its `user_config_schema`; we fill *its* variables (account / partition / walltime / nodes), never an arbitrary template. **Verified (SDK 4.13.0):** there is **no first-class schema fetch** — `Client.get_endpoint_metadata(uuid)` returns config *values* (best-effort), not a structured `user_config_schema`. But the web service **validates `user_endpoint_config` server-side at submit** — a bad key/value is rejected regardless — so the schema is a *UX nicety* (offer the right partitions up front), not a correctness gate. → **curate the allowed config in the entry; treat `get_endpoint_metadata` as opportunistic; rely on server-side validation as the safety net.**
  59: 3. **Consent — the graceful browser auth.** A Globus Auth consent for the MEP's scope is the irreducible "access" input. It is a **browser OAuth** (authorize URL → approve → return), the *same* UX as the Cloudflare MCP's `authenticate`/`complete_authentication` (loopback + paste-back fallback). Surface it as a new `connect_facility` phase `needs_consent` carrying the authorize URL; reuse the scope machinery (`credentials._missing_scopes` / `login_required`). This is "graceful auth that returns to the terminal," on our real credential — and it *replaces* the SSH bootstrap + storage.db seeding wholesale for MEP facilities.
  60: 4. **Identity mapping** — confirm the facility maps our Globus identity to the intended local account (the SSH replacement); surface a clear failure if it doesn't, rather than a silent wrong-user run.
  61: 
  62: **Where it touches the code:**
  63: - A third `Facility` — **`MEPFacility`** (alongside `SlurmFacility` / `LocalFacility`, the [[facility-base|`Facility` protocol]]) — whose `provision()` does **no SSH**: it returns `EndpointHandle(endpoint_id=compute_mep_uuid, reused=True)` after the consent check; `manager_online` is the web check on the UUID; no `bootstrap`, no `config_template` (the *facility* owns the template).
  64: - `connect_facility` / `ensure_endpoint_up` gain a **MEP branch**: a `compute_mep_uuid` entry builds a `MEPFacility` (replacing the `_unsupported_entry_reason` reject); "provision the compute shape" becomes "submit the UEP config to the MEP." The runner binding — `Executor(uuid, uec)` — is unchanged.
  65: 
  66: > [!warning] Stop/spend does NOT carry over — the honesty guarantee weakens, honestly
  67: > On our personal endpoint, `stop_endpoint` `scancel`s the block over the login shape ([[Cost control]], the `stop_is_honest` fix [#24](https://github.com/ryanchard/hpc-bridge/issues/24)). On a facility MEP **we own neither the manager nor a login channel** — that scancel path doesn't exist. **Verified (SDK 4.13.0): there is no honest foreign-endpoint cancel** — `ComputeFuture.cancel()` only works *pre-run* (a still-queued task), and `Client.stop_endpoint` / `delete_endpoint` act on **our own** registration (calling them on a facility MEP is wrong/unauthorized). So MEP `stop_endpoint` is **`draining`-only** — stop submitting, rely on the MEP's `max_idletime` idle-release — and must **never report `status="down"`** (it can't confirm the block is gone). `teardown_endpoint` is a **no-op** (nothing of ours to destroy). This satisfies `stop_is_honest` by reporting `draining`, not by lying `down`.
  68: 
  69: **Feasibility to settle first:** which target facilities actually run a *targetable* multi-user MEP? NERSC runs a Globus Compute MEP; does our ACCESS target (Anvil) expose one, or is it SSH-bootstrap-only? Can we submit our own `user_endpoint_config`, or only select a named site preset? These answers size Phase 2.
  70: 
  71: ## Phase 2 milestones (build order)
  72: 
  73: | M | Deliverable | Unlocks |
  74: |---|---|---|
  75: | **M1** | ✅ **MERGED 2026-09-03 ([#41](https://github.com/ryanchard/hpc-bridge/issues/41))**: model tweaks (`ssh_host` optional, `init_blocks`, `account_required`, the `_reachable` + no-client-templating validators) · `MEPFacility` (compute-only, `supported_shapes=("compute",)` — [[facility-mep]]) · `_facility_from_entry` dispatches on `compute_mep_uuid` first · `_shape_reject` at every shape entry point · `_connect_mep` (attach, no block, MEP-specific `needs_account`) · `_stop_mep` draining-only + teardown-as-detach (**M4 folded in**) · the `globus-cluster.yaml` seed (ingested as `globus:globus1`) + skill/command guidance · the live `mep_compute_only` scenario (green 2026-08-19). Follow-ups since: the terminal, sticky NO ACCOUNT ([#49](https://github.com/ryanchard/hpc-bridge/issues/49)); the `access`/`access_note` summaries and the identity-blind-attach wording ([#50](https://github.com/ryanchard/hpc-bridge/issues/50)) | catalog-driven MEP dispatch — **live on globus1** |
  76: | **M2** | `needs_consent` phase + the browser-OAuth (Globus consent) flow | **the graceful-auth win** — zero SSH, zero Duo. NB: globus1 is consent-free, so validate against a **consent-gating** facility |
  77: | **M3** | Curate the allowed `user_endpoint_config` in the entry; best-effort `get_endpoint_metadata`; lean on server-side validation | correct billed runs |
  78: | **M4** | Honest MEP stop: `draining`-only (idle-release); `teardown` a no-op — **built as part of M1** (`_stop_mep`: draining is FINAL on a MEP, the notice names the idle-release tail and says don't re-poll; teardown detaches) | the semantics gap (no foreign cancel API) |
  79: 
  80: **M1 + M2 is the V1 story:** a catalogued MEP facility, zero SSH, graceful consent. On the **globus1 testbed specifically, M1 alone** already delivers zero-SSH (it's consent-free); M2 is proven against a consent-gating facility.
  81: 
  82: > [!important] Superseded (2026-08-21): V1 ships on M1 alone — M2 is deferred to V1.x
  83: > The scope decision in [[V1 release]]: V1 supports zero-SSH MEP dispatch **for consent-free facilities** (validated live) plus the SSH path; the consent flow (M2) waits for a facility that can actually exercise it. Gating V1 on M2 meant gating it on infrastructure we don't have.
  84: 
  85: ## Guiding invariants (must hold across both phases)
  86: - **Hot path stays token/AMQP — no new SSH channel** ([[Two-channel architecture]]). Reuse and MEP consumption *remove* SSH; neither adds a work channel.
  87: - **hpc-bridge still only ever *creates* personal endpoints** — `--multi-user false` stays for anything we stand up ([[MEP & templated endpoints]]). Phase 2 *consumes* a facility MEP; it never makes hpc-bridge run one.
  88: - **Discovery proposes; the user confirms/consents** — a discovered MEP UUID/schema is a session-local candidate, never auto-trusted ([[Discovery channel model]]).
  89: - **Stop stays honest on every channel** ([#24](https://github.com/ryanchard/hpc-bridge/issues/24)).
  90: 
  91: ## Deferred
  92: Identity-mapping edge cases and stale-consent handling; MEP-side allocation/quota reporting — without a login channel there's no `mybalance`, so fall to the account-named spend gate (the `entry.allocation is None` path) unless a facility exposes a balance API.
  93: 
  94: ## See also
  95: [[facility-mep]] · [[MEP & templated endpoints]] · [[MEP facilities survey]] · [[Discovery channel model]] · [[Globus index discovery channel]] · [[Standing up the endpoint]] · [[Cost control]] · [[Two-channel architecture]] · [[facility-remote]] · [[login]]
  96: 
  97: ## No account at the facility (the unmapped-identity failure)
  98: 
  99: What happens when someone WITHOUT a local account connects to a MEP facility (asked 2026-09-03; answered from the endpoint source, `globus_compute_endpoint/endpoint/endpoint_manager.py`): `connect_facility` still **attaches** (the manager is online and public — `needs_account`/`reused=True`), because nothing identity-specific happens until a task is submitted. The first submit (our warmth canary behind the spend gate) makes the web service ask the root manager to start a user endpoint for the caller's identity set; the manager runs the identity mapper and, on no match, logs `Identity failed to map to a local user name.` and sends a **failure notice** that the web service delivers as the task's failure reason — our canary future raises with that text; no user endpoint ever starts, no block is queued, nothing is billed. (Two siblings: `…mapped to a local user name, but local user does not exist` and, for a single-user endpoint, `Ignoring start request for untrusted identity`.) Before 2026-09-03 hpc-bridge showed this as **`provisioning` / "allocating nodes…" with the error appended, forever** (a non-timeout canary failure only marked the runner stale). Now `_no_account_failure` recognises the three messages and `ensure_endpoint_up` returns a **terminal `down`** (and a cold `run_shell` a terminal `failed`) whose notice names the refused Globus identity (best-effort `globus_identity_label`, openid userinfo through the stored login) and says what to do: an account on the machine + the identity in the endpoint's mapping, via facility support. **Not yet reproduced live** — the harness and the maintainer share one Globus identity (mapped to `glabs`); the live check is a fresh-user run logged in as a *different* identity (e.g. the maintainer's Google identity) against `globus1`.
 100: 
 101: **Reproduced live 2026-09-03** (`agentic/mep_no_account_check.py`, maintainer signed in as a separate, unlinked Globus account `ellermaugustus@gmail.com`; first attempt slipped through as the mapped identity because `openid`-only userinfo carries no username — fixed: the driver resolves the *effective* identity via `get_identities`). `connect_facility` → `needs_account`/`reused=True` (attach is identity-blind); first `ensure_endpoint_up` → the canary got exactly the documented 422 — `ComputeAPIError[SEMANTICALLY_INVALID]: Request payload failed validation: Identity failed to map to a local user name. (LookupError) Globus effective identity: a4ef1d60-… Globus username: ellermaugustus@gmail.com` — and hpc-bridge answered a terminal `down` naming the identity. **Second call, 2 s later, exposed a gap:** the re-submitted canary got a transient `RESOURCE_CONFLICT` ("Endpoint … is already in use: possibly due to concurrent requests -- please try again") and the verdict flipped back to "allocating nodes… fix the config/partition". Fixed: the no-account verdict is **sticky on the shape runtime** (`ShapeRuntime.no_account`; `_confirm_worker` returns without submitting; a cold `run_shell` is `failed` the same way), cleared by a re-bind/teardown or a new login (`_forget_identity_verdicts`); and a `RESOURCE_CONFLICT` is labelled TRANSIENT ("wait ~10 s and call again") rather than a config error. Note the canary capture also had to keep the API error's `.message` — the 422's repr spends ~190 chars on the URL before the message.
 102: 
 103: **Verified end to end 2026-09-03.** Driver re-run after the sticky fix: two identical terminal `down`s, one submit. Agent-level (`FRESH=~/hpcb-noaccount scripts/fresh_user_session.sh`, "connect me to globus1", spend confirmed): the agent called `ensure_endpoint_up` once, reported "a hard stop, not a queue wait", quoted the Globus username, the effective-identity UUID and the endpoint UUID, said what unblocks it (a local account + the identity in the endpoint's mapping, via the cluster's admins), declined to call again until told, and offered another facility. Maintainer's verdict: behaviour OK. Follow-up: the harness scenario `mep_no_account` (a second, unmapped identity's `storage.db` mounted via the `GLOBUS_DB_SECRET` knob) is in **PR [#51](https://github.com/ryanchard/hpc-bridge/issues/51) (open)** — its first sweep also found that two cells sharing one identity make the web service answer the second with `RESOURCE_CONFLICT` on every submit, and an agent retried the "TRANSIENT — call again" hint 7×; that PR caps consecutive transient conflicts (`TRANSIENT_CONFLICT_LIMIT` = 3 → a `down` naming the likely cause) and runs such scenarios `SERIAL`.
```
</details>


# ITEM 16

## ep:Planned/Globus index discovery channel.md|2026-09-23T00:56:21Z|sha256:eec54|src/hpc_bridge/server.py#_unsupported_entry_reason
**episode** · note `Planned/Globus index discovery channel.md` · seq 11 · commit f7e2fbc2 · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#_unsupported_entry_reason` _unsupported_entry_reason — **body**  (note lines [29])
  ```
  was: def _unsupported_entry_reason(entry) -> str | None:
    """Why this catalog entry can't drive a stand-up yet (v1: SSH-bootstrap Slurm only), or None."""
    if entry.compute_mep_uuid:
        return (
            "entry has a compute_mep_uuid (BYO multi-user endpoint); catalog-driven MEP dispatch "
            "is not wired yet — use HPC_BRIDGE_ENDPOINT_ID"
        )
    if entry.compute.scheduler != "slurm":
        return f"scheduler {entry.compute.scheduler!r} not supported yet (slurm only)"
    return None
  ---
  now: def _unsupported_entry_reason(entry) -> str | None:
    """Why this catalog entry can't drive a stand-up yet (v1: SSH-bootstrap Slurm/PBS only), or None."""
    if entry.compute_mep_uuid:
        return (
            "entry has a compute_mep_uuid (BYO multi-user endpoint); catalog-driven MEP dispatch "
            "is not wired yet — use HPC_BRIDGE_ENDPOINT_ID"
        )
    if entry.compute.scheduler not in ("slurm", "pbs"):
        return f"scheduler {entry.compute.scheduler!r} not supported yet (slurm/pbs only)"
    return None
  ```

<details><summary>note</summary>

```
   1: # Globus index discovery channel
   2: 
   3: > [!warning] Planned · transient
   4: > **Plans 1–2 (catalog data layer + agentic selection flow) are merged**, as is the **discover-first sweep + persistent SSH** (this note's "built" sections). Tracking: [#7](https://github.com/ryanchard/hpc-bridge/issues/7). This note is the spec + status; it churns as the work lands — remaining: seed-emission / write-back.
   5: 
   6: ## Goal
   7: 
   8: Replace the hardcoded `anvil_profile` ([[facility-remote]]) with a **catalog-driven resolver** that builds a `MachineProfile` from an entry in a self-owned **Globus Search index** — so adding a facility is *data*, not *code*. The index is the *happiest* discovery channel; everything else (login-node probe, the human) is fallback. Contrast with what exists now: [[Discovery today]].
   9: 
  10: ## Design — as built (Plan 1)
  11: 
  12: The conceptual frame (channel model, provide-vs-discover matrix, principles, the trace) lives in **[[Discovery channel model]]**. A `catalog/` package implements the resolver:
  13: 
  14: - **`CatalogEntry`** (Pydantic) — `compute:` (pinned, user can't override) / `defaults:` (overridable) split; named allocation `parser`; `{user}`/`{venv}` templating; `worker_init` *derived*; `account` *not* stored; UUIDs validated on read. `profile_kwargs()` is the binding seam → `MachineProfile`.
  15: - **`CatalogProvider`** seam — `SearchCatalog` (live `get_subject` → write-through cache; **no bundled fallback** — an index miss is `None`), `BundledCatalog` (the seed loader — curator ingest source + test fixture, *not* a runtime catalog), `FakeCatalog` (the test double).
  16: - **`make_facility`** — `HPC_BRIDGE_MACHINE` → catalog; else local (the agent binds a machine at runtime via `connect_facility`). The hardcoded `anvil_profile` + `HPC_BRIDGE_FACILITY` path is **removed**, and so is the bundled-seed fallback; the Globus index is the only runtime source.
  17: - **Trust** — the plugin is **read-only**; writes are **curator-only** via the `hpc-bridge-catalog` ingest (PR review = the audit trail), because an open-write catalog of executable config (`env_setup` bash, UUIDs) is an injection vector. A `CatalogSummary` is the **agent-safe view** (no executable config / raw UUIDs). `provenance: plugin-validated` is *reserved, not built* — this supersedes our earlier "plugin write-back loop."
  18: 
  19: > [!note] Decided — authenticated read (reuse the Compute identity)
  20: > We already require Globus Auth for Compute, so the index reuses **the same identity** (`SearchClient(app=Client().app)`) rather than an anonymous client. Rationale: the curator/write path needs auth *anyway* (ingest → `search:all`, else `403`), so unified auth is the coherent model — and it unlocks **`visible_to`-restricted entries** (a facility's config / sensitive UUIDs visible only to its allocation-holders), the actual reason to use Globus Search over a checked-in file. The marginal cost is a **one-time search-scope consent** per identity that wants *live* reads (run `hpc-bridge-catalog`; the server never prompts and **hard-fails** until granted — no bundled fallback). *(Reading purely-public entries anonymously, to skip even that consent, stays available as a later optimization.)*
  21: 
  22: ## Plan 2 — built (the agentic selection flow)
  23: 
  24: Machine + allocation are now **agent-chosen at runtime**, not fixed by env ([[The MCP tools]]):
  25: - **`list_facilities(query)`** → browse the catalog (agent-safe `CatalogSummary`s).
  26: - **`connect_facility(facility)`** → bind the machine (late-binds `AppCtx.facility`, resetting shapes/state on a switch), bring up its **free login shape** (SSH cold-bootstrap once, or reuse an online endpoint), run the allocation command over Compute, parse, and return `needs_account` with the allocations. `provisioning` ⇒ login node still warming.
  27: - **deterministic parsers** (`catalog/parsers.py`): `mybalance` built (real Anvil output); `sbank`/`iris` reserved. Stdout parsed in code, never handed to the model.
  28: - **`ensure_endpoint_up(account=…)`** → the chosen allocation threads into the Slurm shape's `user_endpoint_config` (mirrors `partition`); `account` is no longer env-only.
  29: - `_facility_from_entry` / `_unsupported_entry_reason` factored out of `make_facility`'s startup path and shared with `connect_facility`.
  30: 
  31: ## The Socratic fallback — built (session-local)
  32: 
  33: A machine the index can't resolve is **no longer a hard failure**. `connect_facility(X)` returns `phase="needs_facility_details"`; the agent elicits the config from the **user** (the `FacilityDetails` schema is the question list — `ssh_host`, `interface`, `env_setup`, `scratch_root`, `partition`, optional allocation command), calls `connect_facility(X, details=…)`, and the server builds a **session-local** `CatalogEntry` (`provenance="session"`, remembered on `AppCtx.session_facilities`), then runs the **normal** flow. The login-shape canary **validates** the supplied values (a wrong `interface`/`env_setup` ⇒ the worker never registers) — *elicit-then-validate*, the [[Discovery channel model|human channel]] wired in.
  34: 
  35: - **Trust:** the session-local entry holds executable config (`env_setup`, `ssh_host`) but it's **user-supplied** (Tier-1, like credentials), **never written to the index** (curator-only writes stay the boundary). The agent is a conduit for the user's answers; it must not *invent* config — it **proposes discovered facts** for the user to confirm. SSH user + key come from `~/.ssh/config` (read live; optional env overrides), never a boot-env var the running server can't see.
  36: - **Isolated endpoint name:** a session facility registers as `hpc-bridge-<facility>` (e.g. `hpc-bridge-globus`), never the bare `hpc-bridge`. Globus Compute keys endpoints by *identity + name*, so a shared name lets `find_online_endpoint` reuse another facility's (or a stale "online") registration — stranding a canary that can never warm. `_entry_from_details` derives it for session facilities; curated seeds set it explicitly (e.g. `hpc-bridge-anvil`). **The standard is `hpc-bridge-<facility>` everywhere — the bare `hpc-bridge` is banned.**
  37: - **Also covers index-down:** if `make_catalog()` errors, the same fallback fires (supply `details` to proceed) rather than a hard fail.
  38: - **Deferred:** write-back / seed-emission for curation; parsers beyond `mybalance`; persisting session facilities across restarts; non-Slurm.
  39: 
  40: ### Discover-first — built (this branch)
  41: 
  42: Pure elicitation was too much to ask: `interface` / `env_setup` / `scratch_root` / `partition` are facts the login node can *tell* you. So an index miss now **discovers before it asks**. `connect_facility(X, ssh_host="…")` builds a **bare `SshTarget`** (just `ssh_host` + env creds — nothing else from `FacilityDetails` is needed to open SSH), runs **one batched login-node probe** ([[discovery|discovery.py]] · `discover_facility_details`), and returns `phase="proposed_facility_details"` with a filled-in `FacilityDetails` **draft** + notes flagging the low-confidence fields. The agent reviews/corrects the draft *with the user* (above all `interface`) and calls `connect_facility(X, details=…)`, re-entering the **same** session-local flow above — the canary still validates. With no host, `needs_facility_details` simply asks for one. `_propose_or_ask` (`server.py:796`) is the router; the probe rides the persistent-SSH ([[facility-remote]]) master the bootstrap then reuses (no extra auth).
  43: 
  44: The [[Discovery channel model|human channel]] minimized: **the user provides access, the agent discovers the config.** "Elicit-then-validate" becomes **probe → propose → confirm → validate** — proposing *discovered* facts (user-confirmed, canary-checked) is not "inventing."
  45: 
  46: ## Our extras (later slices, optional)
  47: 
  48: From [[Discovery channel model]], not in the catalog yet: per-channel **ablation flags** + the **resolution trace** (resolution is single-source so a per-fact trace is less load-bearing today). Fold in if/when the matrix-as-tests discipline is wanted.
  49: 
  50: ## Status
  51: 
  52: - **Merged:** Plan 1 (catalog data layer · catalog-driven `make_facility` · `hpc-bridge-catalog` ingest, [#15](https://github.com/ryanchard/hpc-bridge/pull/15)) **and** Plan 2 (`list_facilities` + `connect_facility` + `mybalance` parser + account-from-selection, [#17](https://github.com/ryanchard/hpc-bridge/pull/17)).
  53: - **Built + merged:** the **Socratic fallback** + **discover-first sweep** above — `connect_facility(ssh_host=…)` → `proposed_facility_details` → confirm → session-local `connect_facility(details=…)` — plus persistent SSH ([[facility-remote]], ControlMaster). Validated live on the globus1 cluster.
  54: - **Deferred:** ACCESS MCP / Operations API channels; the ablation/trace extras; seed-emission/write-back (see [[Discovery channel model]]).
  55: 
  56: ## See also
  57: [[Discovery channel model]] · [[Discovery today]] · [[facility-remote]] · [[Happy path]] · [[Home]]
```
</details>


# ITEM 17

## ep:Modules/facility-remote.md|2026-09-23T00:56:09Z|sha256:aeb2a|src/hpc_bridge/facility/remote.py#profile_from_catalog_entry
**episode** · note `Modules/facility-remote.md` · seq 4 · commit d342e72b · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/facility/remote.py#profile_from_catalog_entry` profile_from_catalog_entry — **body**  (note lines [9])
  ```
  was: def profile_from_catalog_entry(
    entry: CatalogEntry,
    *,
    user: str,
    account: str,
    partition: str | None = None,
    venv: str | None = None,
) -> MachineProfile:
    """Build a `MachineProfile` from a catalog entry plus per-user runtime values.

    The catalog stores user-agnostic templates; this resolves them at provision time:
    ``{user}`` is the SSH login user and ``{venv}`` is the remote globus-compute-endpoint venv
    (defaults to the ``/home/{user}/hpc-bridge/gce-venv`` convention). ``account`` and the derived
    ``worker_init`` (= the resolved ``env_setup``, repl
  ---
  now: def profile_from_catalog_entry(
    entry: CatalogEntry,
    *,
    user: str,
    account: str,
    partition: str | None = None,
    venv: str | None = None,
) -> MachineProfile:
    """Build a `MachineProfile` from a catalog entry plus per-user runtime values.

    The catalog stores user-agnostic templates; this resolves them at provision time:
    ``{user}`` is the SSH login user and ``{venv}`` is the remote globus-compute-endpoint venv
    (defaults to the ``/home/{user}/hpc-bridge/gce-venv`` convention). ``account`` and the derived
    ``worker_init`` (= the resolved ``env_setup``, repl
  ```

<details><summary>note</summary>

```
   1: # facility-remote.py — `facility/remote.py`
   2: 
   3: > [!abstract] Role
   4: > Everything machine-specific for a remote Slurm cluster, behind one [[facility-base|Facility]]: the SSH transport, the per-facility `MachineProfile`, the `globus-compute-endpoint` CLI driver, and `SlurmFacility` (bootstrap / provision / teardown / config template).
   5: 
   6: ## The pieces
   7: 
   8: - **SSH transport** — `SshTarget` (`:37`) + `ssh_exec()` (`:55`): key-only (`BatchMode`, `IdentitiesOnly`), reaps the child on timeout/cancel (no process/FD leak). The control channel of [[Two-channel architecture]].
   9: - **Per-facility data** — `MachineProfile` (`:86`): host, `env_setup` (module + venv), `interface`, partition, account, scratch… now supplied by the [[Facility catalog|catalog]] (`profile_from_catalog_entry`), no longer hardcoded per machine.
  10: - **gce driver** — `RemoteEndpointCLI` (`:151`): runs `globus-compute-endpoint` over SSH via `_gce` (`:163`); also `login_exec` (`:167`, backs the `login_shell` tool), `seed_storage_db` (`:238`, [[Credential seeding]]), `configure`/`start`/`stop`, and `cancel_blocks` (`:293`).
  11: - **Orchestration** — `SlurmFacility` (`:355`): `bootstrap` (`:471`), `provision` (`:512`), `config_template` (`:378`, [[MEP & templated endpoints]]), `teardown` (`:545`), `manager_online` (`:562`, web), `find_online_endpoint` (`:569`, web reuse).
  12: 
  13: ## How a stand-up flows
  14: 
  15: `bootstrap` (`:471`) is the entry point, and it is **reuse-or-SSH**: it first asks the Globus *web* service whether we already own an online endpoint (`find_online_endpoint`, `:569`) → reuse over AMQP, **zero SSH**. Only if none is online does it seed credentials (when needed) and call `provision` (`:512`): `configure` if absent → write the engine-free manager `config.yaml` + the UEP template → `start` (detached) → capture & **pin** the login node. See [[Standing up the endpoint]].
  16: 
  17: > [!warning] Login-node pinning
  18: > The manager lives on ONE login node, but HPC SSH aliases round-robin. `start` (`:267`) captures the FQDN *in the same SSH connection* that launches the daemon (a separate probe could resolve a different node), records it via [[state]]'s `LoginNodeStore`, and the CLI `rebind`s straight there next session.
  19: 
  20: > [!warning] `gce list` parsing is fail-loud
  21: > `status`/`endpoint_id` parse `gce list`'s ASCII pipe-table via `_parsed_rows` (`:201`); a gce version/format change **raises** rather than being misread as "no endpoints" (which would trigger a wrong re-provision). See [#8](https://github.com/ryanchard/hpc-bridge/issues/8).
  22: 
  23: > [!note] SSH-once
  24: > `find_online_endpoint` reuse is the keystone that lets a reconnect session avoid SSH entirely — the load-bearing mitigation for MFA facilities ([#3](https://github.com/ryanchard/hpc-bridge/issues/3)). See [[Two-channel architecture]] and [[Discovery today]].
  25: 
  26: ## See also
  27: [[Standing up the endpoint]] · [[Credential seeding]] · [[MEP & templated endpoints]] · [[facility-base]] · [[state]] · [[credentials]]
```
</details>


# ITEM 18

## ep:Modules/server.md|2026-09-23T01:10:08Z|sha256:cf57a|src/hpc_bridge/server.py#_ensure_endpoint_up
**episode** · note `Modules/server.md` · seq 133 · commit 6922bba3 · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#_ensure_endpoint_up` _ensure_endpoint_up — **body**  (note lines [16, 36, 40, 62])
  ```
  was: async def _ensure_endpoint_up(
    app: AppCtx,
    shape: str = DEFAULT_SHAPE,
    partition: str | None = None,
    confirm_spend: bool = False,
    account: str | None = None,
) -> EndpointStatus:
    if reject := _shape_reject(app, shape):  # compute-only facility: never build a login runtime
        return EndpointStatus(
            status="down", block_state="cold", endpoint_id=app.state.endpoint_id, notice=reject,
        )
    if partition is not None and not _VALID_PARTITION.match(partition):
        return EndpointStatus(
            status="down",
            block_state="cold",
  
  ---
  now: async def _ensure_endpoint_up(
    app: AppCtx,
    shape: str = DEFAULT_SHAPE,
    partition: str | None = None,
    confirm_spend: bool = False,
    account: str | None = None,
) -> EndpointStatus:
    if reject := _shape_reject(app, shape):  # compute-only facility: never build a login runtime
        return EndpointStatus(
            status="down", block_state="cold", endpoint_id=app.state.endpoint_id, notice=reject,
        )
    if partition is not None and not _VALID_PARTITION.match(partition):
        return EndpointStatus(
            status="down",
            block_state="cold",
  
  ```

<details><summary>note</summary>

```
   1: # server.py
   2: 
   3: > [!abstract] Role
   4: > The FastMCP server — the agent-facing entry point. Declares the **eleven** MCP tools, holds session state (`AppCtx`), gates on the Globus login, selects/binds the facility (SSH personal endpoint or facility MEP), and runs the provision → canary → dispatch → spend flow under a lock.
   5: 
   6: ## What it does
   7: 
   8: `server.py` is the runtime heart. It exposes eleven tools ([[The MCP tools]]), each a thin `@mcp.tool()` wrapper over a private `_`-helper that takes the `AppCtx`:
   9: 
  10: | Tool | Helper | Does |
  11: |---|---|---|
  12: | `list_facilities` | `_list_facilities` | browse the public registry ([[Facility catalog]]) — anonymous, agent-safe summaries with `access`/`access_note` |
  13: | `connect_facility` | `_connect_facility` | **login gate first**, then resolve (details → registry → cache → probe) and bind: bring up the login shape + list allocations (SSH), or attach with zero SSH (`_connect_mep`) |
  14: | `authenticate` | `_authenticate` | the Globus login gate as a tool: arm a login (browser loopback / paste), wait, report `LoginStatus` |
  15: | `complete_login` | `_complete_login` | finish a paste-mode login with the one-time auth code |
  16: | `ensure_endpoint_up` | `_ensure_endpoint_up` | provision/probe; report warm via the canary; thread account/partition; surface pilot state, dispatch failures, the terminal NO ACCOUNT |
  17: | `run_shell` | `_run_shell` | dispatch a command to the warm block / login shape; hand back a poll handle past the sync-wait |
  18: | `poll_task` | `_poll_task` | retrieve a long task's result; ORPHANED when its endpoint is gone |
  19: | `reset_session` | `_reset_session` | clear a session's cwd/env |
  20: | `stop_endpoint` | `_stop_endpoint` / `_stop_mep` | release the block over AMQP and leave the manager online (SSH), or drain honestly (MEP) |
  21: | `stop_endpoint` (live task) | `_stop_endpoint` | REFUSES (status `up`, names the task) while a compute task is RUNNING — releasing the block does not end the task; the endpoint relaunches a block for it (fake-cluster chaos `stop_while_running`, 2026-09-05). Same rule as `_stop_mep`. |
  22: | `teardown_endpoint` | `_teardown_endpoint` | fully destroy the endpoint (`gce stop` + delete over SSH) — or, on a MEP, detach. The block release is AMQP and synchronous; the SSH half runs in `app.teardown_task` (`_finish_teardown`) and one call waits `_TEARDOWN_SYNC_WAIT_S` (60 s) for it, else answers `tearing_down` — Expanse's stop + delete take ~3 min (live 2026-09-04), past a client's tool window. On an `mfa-otp` facility `_teardown_preauth_gate` asks for the one-time code first. The report's `ssh_closed` is spoken in the notice |
  23: | `login_shell` | `_login_shell` | read-only login-node command over SSH (cold-start escape hatch); refused on a MEP |
  24: 
  25: (Helpers carry the logic; the `@mcp.tool()` wrappers are thin. Exact line numbers drift — grep the symbol.)
  26: 
  27: ## How it works
  28: 
  29: - **State.** `AppCtx` (`:85`) holds the facility, profile, endpoint state, the per-shape `ShapeRuntime` (`:44` — its Executor, canary result, spend clock, the sticky `no_account` verdict, `spend_confirmed`), the live `TaskHandle`s (`:71`), the session-local facilities dict, the `LoginFlow` ([[login]]), and an `asyncio.Lock`. `lifespan` (`:423`) builds it from `make_facility` + env and installs the real `LoginFlow`.
  30: - **The Globus login gate.** `_connect_facility` (`:1115`) checks `login_flow.login_required()` **before the catalog read and before any SSH** — every non-`unsupported` outcome needs Globus, and constructing the SDK `Client` for the catalog on a fresh install would run the SDK's *own* command-line login on the MCP transport. `_start_login_and_wait` (`:1313`) arms the flow and, in browser mode, **waits** `_login_wait_s()` (`:1306`, `HPC_BRIDGE_LOGIN_WAIT_S` = 90 s) for the redirect to land — then the connect simply continues; a browser attempt that fails during the wait is re-armed in paste mode. Otherwise `_needs_login_result` (`:1355`) returns `phase="needs_login"` with the URL and the agent-facing instructions (`_login_notice`, `:1327`: relay the link, single-use, never a password). `_authenticate` (`:989`) / `_complete_login` (`:1004`) are the same flow as tools; both call `_forget_identity_verdicts` (`:1856`) on success — a new login may be a different identity, so sticky no-account verdicts are dropped and runners rebuilt.
  31: - **Facility selection.** `make_facility` (`:315`) returns a facility resolved from the [[Facility catalog|registry]] (`HPC_BRIDGE_MACHINE`, via `_catalog_facility` `:282`) or a `LocalFacility`. `_facility_from_entry` (`:248`) is the shared seam: a `compute_mep_uuid` entry → `MEPFacility` ([[facility-mep]]) — **MEP wins**; else `profile_from_catalog_entry` + `_slurm_facility` (`:203`), which reads the login-node pin from [[state]] and rebinds the CLI to it. `make_catalog` (`:373`) reads the registry with a **built-in** id (`PUBLIC_REGISTRY_INDEX`; `HPC_BRIDGE_SEARCH_INDEX` overrides) through `_make_search_client` (`:345`) — **anonymous** unless the Compute identity already holds the Search scope; it never triggers a login. `lifespan` **boots resiliently** — a failed `make_facility` (stale env, no registry) warns and starts unbound rather than crashing; `connect_facility` then binds and **moves `scratch_root`** to the facility (`_resolve_scratch_root`, `:331`, [[Session continuity]]). `HPC_BRIDGE_SSH_HOST` overrides the SSH host **only on this startup-pin path** (`_facility_from_entry(pinned_host=…)`); the agentic `connect_facility` path uses the *bound* facility's own `ssh_host`, so a global env can't silently redirect an agent-chosen facility ([#35](https://github.com/ryanchard/hpc-bridge/issues/35)).
  32: - **Resolution precedence in `_connect_facility`.** An explicit `details=` is a (re)definition and overrides everything (and is cached to `facilities.json` via `_facility_store`, `:1063`); else a session-local entry; else **the registry** (`make_catalog().get`); else the local BYO cache (`FacilityStore`, keyed on `ssh_host` — only for ids the registry doesn't know, or when it is unreachable); else `_propose_or_ask` (`:1394`). The registry wins for any catalogued id (decision 2026-09-03, [#49](https://github.com/ryanchard/hpc-bridge/issues/49): a stale SSH-era `globus1` cache would have shadowed the MEP entry).
  33: - **Un-indexed discovery.** `_propose_or_ask` builds a bare `SshTarget` (SSH user from `_ssh_config_user` / `ssh -G`, `:118`; key + host from `~/.ssh/config` + env) and runs the [[discovery]] probe → `proposed_facility_details`, or `needs_preauth` (`_needs_preauth_result`, `:1366`, carrying `preauth_command` — [[MFA and interactive SSH auth]]). On confirm, `_entry_from_details` (`:1071`) builds a session-local entry whose endpoint name comes from `_session_endpoint_name` (`:1052`) — `hpc-bridge-<ssh_host slug>`, keyed on the SSH host (`HPC_BRIDGE_ENDPOINT_NAME` overrides it for harness run isolation). `_control_settings` (`:136`) configures the shared ControlMaster ([[facility-remote]]), with `_short_control_dir` (`:161`) keeping the socket path under the Unix cap.
  34: - **Two kinds of bind.** After the bind, `_connect_facility` asks `_has_login_shape` (`:485`, from `_supported_shapes` `:475` — `getattr(facility, "supported_shapes", SHAPES)`). With a login shape it provisions `login`, then runs the allocation command over Compute → `needs_account`; a bootstrap SSH failure is rewritten by `_explain_provision_error` (`:170`) into `NO SSH ACCESS to <host> as <user>` / `CANNOT REACH <host>` ([[Standing up the endpoint]]). Without one — a facility MEP — `_connect_mep` (`:1258`) only **attaches** (reads the manager's status; an OFFLINE manager is a `failed` naming the facility as owner) and returns `needs_account` with `reused=True`, saying whether an account is needed (`account_required`) and that attaching does *not* test the identity mapping. `_shape_reject` (`:489`) then refuses the `login` shape at every entry point (`ensure_endpoint_up`, `run_shell`, `reset_session`, `login_shell`) before a `ShapeRuntime` exists.
  35: - **The provision choke point.** `_provision` (`:725`): the spend floor → bootstrap if there's no endpoint → `ensure_warm` ([[lifecycle]]) → on `"warm"`, confirm a *live worker* via `_confirm_worker` (`:593`, the canary) → `_settle_billing`. Both `ensure_endpoint_up` and `run_shell` (via `_ensure_warm_runner`, `:1936`) reach it. A non-timeout canary failure marks the runner stale (`runner_stale`, rebuilt by `_runner_for` `:570`) and keeps the failed `CanaryResult`; `_dispatch_error_suffix` (`:1837`) puts its text on the `provisioning` notice, labelling a 409 `RESOURCE_CONFLICT` as TRANSIENT (`_transient_dispatch_failure`, `:1849`).
  36: - **The terminal NO ACCOUNT ([[facility-mep]]).** `_no_account_failure` (`:1877`) matches the MEP manager's identity-mapping refusals (`_NO_ACCOUNT_MARKERS`, `:1870`); `_confirm_worker` records the verdict on `ShapeRuntime.no_account` (**sticky** — later calls return without re-submitting), and `_ensure_endpoint_up` returns a terminal `down` / `_cold_outcome` (`:1905`) a terminal `failed` whose `_no_account_notice` (`:1891`) names the identity — from the error itself (`_identity_from_error`, `:1885`) or `globus_identity_label` ([[login]]) — and says what unblocks it. Cleared by a re-bind, teardown, or a new login.
  37: - **The lock.** Serialises provision / runner-swap / stop so concurrent tool calls can't race `AppCtx`. Dispatch happens *outside* the lock, so a long command doesn't serialise everything else. `_stop_endpoint` (`:1680`) cancels the block over the login shape (AMQP) via `_release_blocks_over_login` (`:1497`; `scancel` on Slurm, `qdel` on PBS, matched by the `uep.<eid>` marker), then drops the billed shape (`_drop_compute_shape`, `:1614`) — leaving the manager online for reuse; unconfirmed ⇒ `draining` ([#24](https://github.com/ryanchard/hpc-bridge/issues/24)). On a MEP `_stop_mep` (`:1633`) is **draining-only and terminal** (no cancel channel; refuses while a task still runs), and `_teardown_endpoint` (`:1725`) is a **detach** ([[Cost control]]). The runner `close()` is non-blocking ([[runner]]) so a stop returns promptly.
  38: - **Long-task poll handles ([#21](https://github.com/ryanchard/hpc-bridge/issues/21)).** A command that outlives the sync-wait is registered in `AppCtx.tasks` (`_register_task`, `:1971`) and returned as `phase="running"`; `_poll_task` (`:2123`) reaps it via `_resolve_task` (`:1999`). A live task short-circuits the warmth [[Warmth, the canary & cold-start|canary]], blocks a same-session second dispatch (`_busy_session`, `:1949`) **and** a partition/account change (both would corrupt or cancel it), and every block-close site drains the registry (`_drain_shape_tasks`, `:560`). A pending task whose endpoint is unbound or reports offline is **ORPHANED** — `_endpoint_gone` (`:2097`) / `_orphaned_outcome` (`:2110`): a terminal `failed`, handle dropped, instead of `running` forever ([#44](https://github.com/ryanchard/hpc-bridge/issues/44); a killed block under a *live* endpoint still reads `running` — Parsl relaunches it).
  39: - **The spend floor.** `_provision` returns `"needs_confirmation"` for a billed (`compute`) shape until `confirm_spend=True` — see [[Resource shapes & the spend floor]]. Partition/account selection is threaded in via `_apply_partition` (`:761`) / `_apply_account` (`:787`) after `_VALID_PARTITION`/`_VALID_ACCOUNT` (`:757`) validate the token. `_needs_confirmation_notice` (`:808`) names the free login shape as the alternative only where one exists.
  40: - **Pilot-state observability ([#32](https://github.com/ryanchard/hpc-bridge/issues/32)).** When a billed block stays cold, `_ensure_endpoint_up` (`:826`) enriches the `provisioning` notice with the pilot's ACTUAL scheduler state — read over the login shape (AMQP) by the same `uep.<eid>` marker the release path uses (`_pilot_status_over_login`, `:1589`; `_augment_provisioning_notice`, `:1601`): `RUNNING`/queued/`HELD`, or, past a ~45 s grace (`PROVISION_GRACE_S`, clocked by `ShapeRuntime.provisioning_since`), *"no pilot → likely REJECTED"*. Otherwise a rejected/held `qsub` (bad account, missing `filesystems` directive) is indistinguishable from a normal queue wait — surfaced live on [[Aurora (PBS + bastion) bring-up|Aurora]]. Skipped on a MEP (no login shape); there, "provisioning with no canary ever recorded" means the manager reported OFFLINE, and the notice says so. A warm billed block's notice also carries `_billed_bounds_note` (`:698`) and, with no charge factor configured, says `session_spend: 0` is not a free tier.
  41: 
  42: > [!warning] "warm" means a *worker* answered — not "manager online"
  43: > `manager_online` (a cheap web query) only reflects the login-node manager. In the MEP model the first task forks the UEP and submits the block, so the manager reads online while the next command would cold-start. `_confirm_worker` submits a **canary** through the real Executor; only a returned result ⇒ warm. `CANARY_TTL_S` (`:460`) then trusts that for 45 s so an interactive burst doesn't pay the round-trip each call. See [[Warmth, the canary & cold-start]].
  44: 
  45: > [!warning] The login gate must run before the SDK `Client` is built
  46: > `_make_search_client` uses `Client(do_version_check=False)` and `app.login_required()` (non-prompting) precisely because the SDK's version check is an *authenticated* call: on a fresh install it would trigger the SDK's command-line login — a URL on stdout and `input()` on stdin, i.e. the MCP transport (found in the [#48](https://github.com/ryanchard/hpc-bridge/issues/48) review). Keep the gate first in `_connect_facility`.
  47: 
  48: > [!note] In flight (PR [#51](https://github.com/ryanchard/hpc-bridge/issues/51), open)
  49: > Two product changes ride the agentic-scenarios PR: `TRANSIENT_CONFLICT_LIMIT` (three consecutive `RESOURCE_CONFLICT` refusals ⇒ a `down` saying another session with the same identity holds the endpoint — a model sweep showed an agent retrying 7×), and `_propose_or_ask` routing a refused probe SSH through `_explain_provision_error`. On `main` the transient hint repeats and the probe path returns the raw text.
  50: 
  51: ## See also
  52: [[Two-channel architecture]] · [[Warmth, the canary & cold-start]] · [[Resource shapes & the spend floor]] · [[The MCP tools]] · [[login]] · [[facility-mep]] · [[runner]] · [[lifecycle]] · [[facility-remote]] · [[Facility catalog]] · [[Configuration]]
  53: 
  54: > [!note] Split in progress (2026-09-03)
  55: > Step 1 moved the runtime data types (`AppCtx`, `ShapeRuntime`, `TaskHandle`, `DEFAULT_SHAPE`) to [[context]]; `server` re-exports them. The plan and the remaining steps are in [[Review 2026-09-03 — code quality]] §1.
  56: > Step 2 moved the env reads (as typed accessors), the runtime tunables and the ControlMaster settings to [[config]].
  57: > Steps 3–4 moved every pure notice/outcome builder to [[notices]] and the spend clock to [[cost]]; the shape-capability reads (`_supported_shapes`, `_has_login_shape`, `_idle_release_s`) went to [[context]] and the task-ceiling maths (`_parse_hhmmss`, `_task_ceiling_s`) to [[config]]. `server.py` is now ~1810 lines (from 2276).
  58: > Step 5 moved facility/catalog construction to [[binding]] — callers use module attributes; tests patch `binding.*` / `config._control_settings`. `server.py` ≈ 1550 lines.
  59: > Step 6 moved the scheduler ops (block release, pilot status) to [[scheduler_ops]] with the login-shape runner injected (`_login_runner`).
  60: > Steps 7–8 moved the warmth state machine and task-handle bookkeeping to [[warmth]]; tests patch `warmth._provision` / `warmth._drop_compute_shape`.
  61: > Step 9 moved the login gate (`_start_login_and_wait`, `_authenticate`, `_complete_login`) to [[login_gate]].
  62: > Step 10 moved the connect flow to [[connect]] (injected login-shape runner; `server._connect_facility` is a thin wrapper). **Split complete:** `server.py` holds the FastMCP app, `lifespan`, the tool wrappers and the orchestration seams (`_ensure_endpoint_up`, `_run_shell`, `_reset_session`, `_poll_task`, `_stop_*`, `_teardown_endpoint`, `_login_shell`) — ≈820 lines, from 2276 before the split. **NB:** the function-location notes in the body of this page predate the split; the per-module pages ([[context]], [[config]], [[notices]], [[cost]], [[binding]], [[scheduler_ops]], [[warmth]], [[login_gate]], [[connect]]) are authoritative for where a function lives now.
```
</details>


# ITEM 19

## ep:Modules/login_gate.md|2026-09-23T01:01:58Z|sha256:58473|src/hpc_bridge/login_gate.py#_complete_login
**episode** · note `Modules/login_gate.md` · seq 58 · commit 0691fdae · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/login_gate.py#_complete_login` _complete_login — **body**  (note lines [4])
  ```
  was: async def _complete_login(app: AppCtx, code: str) -> LoginStatus:
    flow = app.login_flow
    if flow is None:
        return LoginStatus(phase="failed", notice="no login is waiting — call authenticate() first")
    try:
        await asyncio.to_thread(flow.complete_with_code, code)
    except Exception as exc:  # noqa: BLE001 - a bad/expired code is a structured outcome, not a crash
        return LoginStatus(phase="failed", notice=f"login code not accepted: {type(exc).__name__}: {exc}"[:300]
                           + " — call authenticate() for a fresh link.")
    _forget_identity_verdi
  ---
  now: async def _complete_login(app: AppCtx, code: str) -> LoginStatus:
    flow = app.login_flow
    if flow is None:
        return LoginStatus(phase="failed", notice="no login is waiting — call authenticate() first")
    try:
        await asyncio.to_thread(flow.complete_with_code, code)
    except Exception as exc:  # noqa: BLE001 - a bad/expired code is a structured outcome, not a crash
        return LoginStatus(phase="failed", notice=f"login code not accepted: {type(exc).__name__}: {exc}"[:300]
                           + " — call authenticate() for a fresh link.")
    _forget_identity_verdi
  ```

<details><summary>note</summary>

```
   1: # login_gate
   2: 
   3: > [!abstract] Role
   4: > The Globus login gate as the tools see it: `_start_login_and_wait` (arm, wait up to `HPC_BRIDGE_LOGIN_WAIT_S` in browser mode and continue in the same call; re-arm in paste mode if the browser attempt dies), and the tool bodies `_authenticate` / `_complete_login`, which also forget the sticky no-account verdicts because a new login may be a different identity.
   5: 
   6: Split step 9 (2026-09-03). The flow machinery stays in [[login]] (kept free of server/runtime imports); this module is the seam between the flow and the runtime. Nothing here is monkeypatched; `server` re-exports the three names and its tools call through the module.
   7: 
   8: ## See also
   9: [[login]] · [[login_flow_manager]] · [[server]] · [[In-terminal Globus login]]
```
</details>


# ITEM 20

## ep:Modules/facility-remote.md|2026-09-23T00:56:09Z|sha256:aeb2a|src/hpc_bridge/facility/remote.py#RemoteEndpointCLI
**episode** · note `Modules/facility-remote.md` · seq 4 · commit d342e72b · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/facility/remote.py#RemoteEndpointCLI` RemoteEndpointCLI — **body**  (note lines [10, 15, 18, 21])
  ```
  was: class RemoteEndpointCLI:
    """Drive `globus-compute-endpoint` on a remote login node over SSH.

    Mirrors the local `EndpointCLI` (configure / start / stop) but runs every
    command inside the remote venv, writes config files over SSH, and reads the
    UUID from `list` (v4 MEP mode does not reliably write endpoint.json)."""

    def __init__(self, target: SshTarget, env_setup: str, *, remote_dir: str = "$HOME/.globus_compute") -> None:
        self.target = target
        self.env_setup = env_setup
        self.remote_dir = remote_dir

    async def _gce(self, *args: str, timeout: float
  ---
  now: class RemoteEndpointCLI:
    """Drive `globus-compute-endpoint` on a remote login node over SSH.

    Mirrors the local `EndpointCLI` (configure / start / stop) but runs every
    command inside the remote venv, writes config files over SSH, and reads the
    UUID from `list` (v4 MEP mode does not reliably write endpoint.json)."""

    def __init__(self, target: SshTarget, env_setup: str, *, remote_dir: str = "$HOME/.globus_compute") -> None:
        self.target = target
        self.env_setup = env_setup
        self.remote_dir = remote_dir

    async def _gce(self, *args: str, timeout: float
  ```
- `src/hpc_bridge/facility/remote.py#RemoteEndpointCLI` RemoteEndpointCLI._gce — **unchanged** RemoteEndpointCLI changed elsewhere (body); RemoteEndpointCLI._gce unchanged (note lines [10, 15, 18, 21])
  ```
  was: async def _gce(self, *args: str, timeout: float = 120.0) -> tuple[int, str, str]:
        inner = f"{self.env_setup} && globus-compute-endpoint " + " ".join(shlex.quote(a) for a in args)
        return await ssh_exec(self.target, f"bash -lc {shlex.quote(inner)}", timeout=timeout)
  ---
  now: async def _gce(self, *args: str, timeout: float = 120.0) -> tuple[int, str, str]:
        inner = f"{self.env_setup} && globus-compute-endpoint " + " ".join(shlex.quote(a) for a in args)
        return await ssh_exec(self.target, f"bash -lc {shlex.quote(inner)}", timeout=timeout)
  ```
- `src/hpc_bridge/facility/remote.py#RemoteEndpointCLI` RemoteEndpointCLI.login_exec — **unchanged** RemoteEndpointCLI changed elsewhere (body); RemoteEndpointCLI.login_exec unchanged (note lines [10, 15, 18, 21])
  ```
  was: async def login_exec(self, command: str) -> tuple[int, str, str]:
        """Run a read-only command on the login node over SSH for facility discovery
        (sinfo/sacctmgr/module). Unlike `_gce` it does NOT source the endpoint venv — base
        login-node tools are already on PATH — and it provisions nothing."""
        return await ssh_exec(self.target, f"bash -lc {shlex.quote(command)}")
  ---
  now: async def login_exec(self, command: str) -> tuple[int, str, str]:
        """Run a read-only command on the login node over SSH for facility discovery
        (sinfo/sacctmgr/module). Unlike `_gce` it does NOT source the endpoint venv — base
        login-node tools are already on PATH — and it provisions nothing."""
        return await ssh_exec(self.target, f"bash -lc {shlex.quote(command)}")
  ```
- `src/hpc_bridge/facility/remote.py#RemoteEndpointCLI` RemoteEndpointCLI.seed_storage_db — **unchanged** RemoteEndpointCLI changed elsewhere (body); RemoteEndpointCLI.seed_storage_db unchanged (note lines [10, 15, 18, 21])
  ```
  was: async def seed_storage_db(self, local_db: Path) -> None:
        """Ship a (trimmed) storage.db to the remote ~/.globus_compute/storage.db.

        The db is binary SQLite, so it rides stdin base64-encoded and is decoded
        remotely. The directory is created 0700 and the file chmod'd 0600 — this is a
        bearer credential. Raises RuntimeError on any remote step failure."""
        payload = base64.b64encode(Path(local_db).read_bytes()).decode("ascii")
        db_path = f"{self.remote_dir}/storage.db"
        rc, out, err = await ssh_exec(
            self.target,
            f'mkdir 
  ---
  now: async def seed_storage_db(self, local_db: Path) -> None:
        """Ship a (trimmed) storage.db to the remote ~/.globus_compute/storage.db.

        The db is binary SQLite, so it rides stdin base64-encoded and is decoded
        remotely. The directory is created 0700 and the file chmod'd 0600 — this is a
        bearer credential. Raises RuntimeError on any remote step failure."""
        payload = base64.b64encode(Path(local_db).read_bytes()).decode("ascii")
        db_path = f"{self.remote_dir}/storage.db"
        rc, out, err = await ssh_exec(
            self.target,
            f'mkdir 
  ```
- `src/hpc_bridge/facility/remote.py#RemoteEndpointCLI` RemoteEndpointCLI.configure — **unchanged** RemoteEndpointCLI changed elsewhere (body); RemoteEndpointCLI.configure unchanged (note lines [10, 15, 18, 21])
  ```
  was: async def configure(self, name: str, multi_user: bool = False) -> None:
        # Force --multi-user false (personal endpoint): the default auto-selects from
        # POSIX caps and can silently create an identity-mapping MEP — see endpoint.py.
        rc, out, err = await self._gce("configure", "--multi-user", "true" if multi_user else "false", name)
        if rc != 0:
            msg = (err or out).strip()
            if "already" in msg.lower() or "configexists" in msg.lower():  # dir exists -> fine
                return
            raise RuntimeError(f"remote configure failed: {msg}")
  ---
  now: async def configure(self, name: str, multi_user: bool = False) -> None:
        # Force --multi-user false (personal endpoint): the default auto-selects from
        # POSIX caps and can silently create an identity-mapping MEP — see endpoint.py.
        rc, out, err = await self._gce("configure", "--multi-user", "true" if multi_user else "false", name)
        if rc != 0:
            msg = (err or out).strip()
            if "already" in msg.lower() or "configexists" in msg.lower():  # dir exists -> fine
                return
            raise RuntimeError(f"remote configure failed: {msg}")
  ```
- `src/hpc_bridge/facility/remote.py#RemoteEndpointCLI` RemoteEndpointCLI.start — **unchanged** RemoteEndpointCLI changed elsewhere (body); RemoteEndpointCLI.start unchanged (note lines [10, 15, 18, 21])
  ```
  was: async def start(self, name: str) -> tuple[str, str | None]:
        # Start the daemon AND capture the login node it landed on in the SAME ssh
        # connection: the alias round-robins, so a separate hostname probe could resolve
        # a different node than the one now hosting the manager daemon. The sentinel
        # isolates the FQDN from gce's own stdout.
        inner = (
            f"{self.env_setup} && globus-compute-endpoint start {shlex.quote(name)} "
            f"--detach && echo HPCB_HOST=$(hostname -f)"
        )
        rc, out, err = await ssh_exec(self.target, f"bash -lc
  ---
  now: async def start(self, name: str) -> tuple[str, str | None]:
        # Start the daemon AND capture the login node it landed on in the SAME ssh
        # connection: the alias round-robins, so a separate hostname probe could resolve
        # a different node than the one now hosting the manager daemon. The sentinel
        # isolates the FQDN from gce's own stdout.
        inner = (
            f"{self.env_setup} && globus-compute-endpoint start {shlex.quote(name)} "
            f"--detach && echo HPCB_HOST=$(hostname -f)"
        )
        rc, out, err = await ssh_exec(self.target, f"bash -lc
  ```
- `src/hpc_bridge/facility/remote.py#RemoteEndpointCLI` RemoteEndpointCLI.stop — **unchanged** RemoteEndpointCLI changed elsewhere (body); RemoteEndpointCLI.stop unchanged (note lines [10, 15, 18, 21])
  ```
  was: async def stop(self, name: str) -> None:
        # Best-effort + bounded: `stop` can throw a psutil traceback yet still cancel the block, and
        # a fresh SSH to a loaded login node is slow — don't let it hold teardown hostage.
        await self._gce("stop", name, timeout=_TEARDOWN_SSH_S)
  ---
  now: async def stop(self, name: str) -> None:
        # Best-effort + bounded: `stop` can throw a psutil traceback yet still cancel the block, and
        # a fresh SSH to a loaded login node is slow — don't let it hold teardown hostage.
        await self._gce("stop", name, timeout=_TEARDOWN_SSH_S)
  ```
- `src/hpc_bridge/facility/remote.py#RemoteEndpointCLI` RemoteEndpointCLI.cancel_blocks — **unchanged** RemoteEndpointCLI changed elsewhere (body); RemoteEndpointCLI.cancel_blocks unchanged (note lines [10, 15, 18, 21])
  ```
  was: async def cancel_blocks(self, endpoint_id: str) -> list[str]:
        """Best-effort `scancel` of THIS endpoint's Slurm blocks; returns the cancelled IDs.

        An ungraceful `stop` (it can die on a psutil traceback) won't scale Parsl's block in,
        so the compute keeps its allocation until walltime. We find our blocks precisely by
        their StdOut path, which Parsl writes under the endpoint's UEP dir
        (`uep.<endpoint_id>.*`) — so we never touch another GlobusComputeEngine endpoint's
        jobs. Never raises: teardown must not crash on a flaky scheduler query."""
        m
  ---
  now: async def cancel_blocks(self, endpoint_id: str) -> list[str]:
        """Best-effort `scancel` of THIS endpoint's Slurm blocks; returns the cancelled IDs.

        An ungraceful `stop` (it can die on a psutil traceback) won't scale Parsl's block in,
        so the compute keeps its allocation until walltime. We find our blocks precisely by
        their StdOut path, which Parsl writes under the endpoint's UEP dir
        (`uep.<endpoint_id>.*`) — so we never touch another GlobusComputeEngine endpoint's
        jobs. Never raises: teardown must not crash on a flaky scheduler query."""
        m
  ```
- `src/hpc_bridge/facility/remote.py#RemoteEndpointCLI` RemoteEndpointCLI.rebind — **unchanged** RemoteEndpointCLI changed elsewhere (body); RemoteEndpointCLI.rebind unchanged (note lines [10, 15, 18, 21])
  ```
  was: def rebind(self, host: str) -> None:
        """Re-point this CLI at a specific host (the pinned FQDN) for reconnect."""
        self.target = replace(self.target, host=host)
  ---
  now: def rebind(self, host: str) -> None:
        """Re-point this CLI at a specific host (the pinned FQDN) for reconnect."""
        self.target = replace(self.target, host=host)
  ```
- `src/hpc_bridge/facility/remote.py#RemoteEndpointCLI` RemoteEndpointCLI.status — **unchanged** RemoteEndpointCLI changed elsewhere (body); RemoteEndpointCLI.status unchanged (note lines [10, 15, 18, 21])
  ```
  was: async def status(self, name: str) -> str | None:
        """'running' | 'configured' | None — drives idempotent (re)provisioning."""
        rc, out, _err = await self._gce("list")
        if rc != 0:
            return None
        for cells in self._parsed_rows(out):
            if cells[-1] == name:  # exact Endpoint Name match, not a line substring
                return "running" if "Running" in cells[1] else "configured"
        return None
  ---
  now: async def status(self, name: str) -> str | None:
        """'running' | 'configured' | None — drives idempotent (re)provisioning."""
        rc, out, _err = await self._gce("list")
        if rc != 0:
            return None
        for cells in self._parsed_rows(out):
            if cells[-1] == name:  # exact Endpoint Name match, not a line substring
                return "running" if "Running" in cells[1] else "configured"
        return None
  ```
- `src/hpc_bridge/facility/remote.py#RemoteEndpointCLI` RemoteEndpointCLI.endpoint_id — **unchanged** RemoteEndpointCLI changed elsewhere (body); RemoteEndpointCLI.endpoint_id unchanged (note lines [10, 15, 18, 21])
  ```
  was: async def endpoint_id(self, name: str) -> str:
        rc, out, err = await self._gce("list")
        if rc != 0:
            raise RuntimeError(f"remote list failed: {(err or out).strip()}")
        for cells in self._parsed_rows(out):
            if cells[-1] == name:  # exact Endpoint Name match, not a line substring
                m = _UUID.search(cells[0])
                if m:
                    return m.group(0)
        raise RuntimeError(f"could not find endpoint {name!r} in `list` output")
  ---
  now: async def endpoint_id(self, name: str) -> str:
        rc, out, err = await self._gce("list")
        if rc != 0:
            raise RuntimeError(f"remote list failed: {(err or out).strip()}")
        for cells in self._parsed_rows(out):
            if cells[-1] == name:  # exact Endpoint Name match, not a line substring
                m = _UUID.search(cells[0])
                if m:
                    return m.group(0)
        raise RuntimeError(f"could not find endpoint {name!r} in `list` output")
  ```
- `src/hpc_bridge/facility/remote.py#RemoteEndpointCLI` RemoteEndpointCLI._parsed_rows — **unchanged** RemoteEndpointCLI changed elsewhere (body); RemoteEndpointCLI._parsed_rows unchanged (note lines [10, 15, 18, 21])
  ```
  was: @classmethod
    def _parsed_rows(cls, out: str) -> list[list[str]]:
        """`_list_rows`, but fail LOUD when `list` clearly emitted an endpoint table we could
        NOT parse (a gce version/format/locale change away from the pipe table) — otherwise an
        unparsed listing reads as "no endpoints" and the caller silently mis-provisions or
        can't find a live endpoint. The legitimate empty case ("No endpoints configured")
        still returns []. See issue #8 (the robust fix is the SDK's get_endpoints())."""
        rows = cls._list_rows(out)
        low = out.lower()
        if 
  ---
  now: @classmethod
    def _parsed_rows(cls, out: str) -> list[list[str]]:
        """`_list_rows`, but fail LOUD when `list` clearly emitted an endpoint table we could
        NOT parse (a gce version/format/locale change away from the pipe table) — otherwise an
        unparsed listing reads as "no endpoints" and the caller silently mis-provisions or
        can't find a live endpoint. The legitimate empty case ("No endpoints configured")
        still returns []. See issue #8 (the robust fix is the SDK's get_endpoints())."""
        rows = cls._list_rows(out)
        low = out.lower()
        if 
  ```

<details><summary>note</summary>

```
   1: # facility-remote.py — `facility/remote.py`
   2: 
   3: > [!abstract] Role
   4: > Everything machine-specific for a remote Slurm cluster, behind one [[facility-base|Facility]]: the SSH transport, the per-facility `MachineProfile`, the `globus-compute-endpoint` CLI driver, and `SlurmFacility` (bootstrap / provision / teardown / config template).
   5: 
   6: ## The pieces
   7: 
   8: - **SSH transport** — `SshTarget` (`:37`) + `ssh_exec()` (`:55`): key-only (`BatchMode`, `IdentitiesOnly`), reaps the child on timeout/cancel (no process/FD leak). The control channel of [[Two-channel architecture]].
   9: - **Per-facility data** — `MachineProfile` (`:86`): host, `env_setup` (module + venv), `interface`, partition, account, scratch… now supplied by the [[Facility catalog|catalog]] (`profile_from_catalog_entry`), no longer hardcoded per machine.
  10: - **gce driver** — `RemoteEndpointCLI` (`:151`): runs `globus-compute-endpoint` over SSH via `_gce` (`:163`); also `login_exec` (`:167`, backs the `login_shell` tool), `seed_storage_db` (`:238`, [[Credential seeding]]), `configure`/`start`/`stop`, and `cancel_blocks` (`:293`).
  11: - **Orchestration** — `SlurmFacility` (`:355`): `bootstrap` (`:471`), `provision` (`:512`), `config_template` (`:378`, [[MEP & templated endpoints]]), `teardown` (`:545`), `manager_online` (`:562`, web), `find_online_endpoint` (`:569`, web reuse).
  12: 
  13: ## How a stand-up flows
  14: 
  15: `bootstrap` (`:471`) is the entry point, and it is **reuse-or-SSH**: it first asks the Globus *web* service whether we already own an online endpoint (`find_online_endpoint`, `:569`) → reuse over AMQP, **zero SSH**. Only if none is online does it seed credentials (when needed) and call `provision` (`:512`): `configure` if absent → write the engine-free manager `config.yaml` + the UEP template → `start` (detached) → capture & **pin** the login node. See [[Standing up the endpoint]].
  16: 
  17: > [!warning] Login-node pinning
  18: > The manager lives on ONE login node, but HPC SSH aliases round-robin. `start` (`:267`) captures the FQDN *in the same SSH connection* that launches the daemon (a separate probe could resolve a different node), records it via [[state]]'s `LoginNodeStore`, and the CLI `rebind`s straight there next session.
  19: 
  20: > [!warning] `gce list` parsing is fail-loud
  21: > `status`/`endpoint_id` parse `gce list`'s ASCII pipe-table via `_parsed_rows` (`:201`); a gce version/format change **raises** rather than being misread as "no endpoints" (which would trigger a wrong re-provision). See [#8](https://github.com/ryanchard/hpc-bridge/issues/8).
  22: 
  23: > [!note] SSH-once
  24: > `find_online_endpoint` reuse is the keystone that lets a reconnect session avoid SSH entirely — the load-bearing mitigation for MFA facilities ([#3](https://github.com/ryanchard/hpc-bridge/issues/3)). See [[Two-channel architecture]] and [[Discovery today]].
  25: 
  26: ## See also
  27: [[Standing up the endpoint]] · [[Credential seeding]] · [[MEP & templated endpoints]] · [[facility-base]] · [[state]] · [[credentials]]
```
</details>


# ITEM 21

## ep:Planned/V1 release.md|2026-09-23T01:01:40Z|sha256:8c6d4|src/hpc_bridge/server.py#complete_login
**episode** · note `Planned/V1 release.md` · seq 48 · commit 05d2f8c6 · state broken

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#complete_login` complete_login — **body**  (note lines [24])
  ```
  was: @mcp.tool()
async def complete_login(code: str, ctx: Context) -> LoginStatus:
    """Finish a paste-mode Globus login with the one-time authorization code the user pasted (from
    the page Globus showed after they approved). Single-use and short-lived — not a password, not a
    token. Only needed when authenticate()/connect_facility reported login_mode="paste"."""
    return await _complete_login(ctx.request_context.lifespan_context, code)
  ---
  now: @mcp.tool()
async def complete_login(code: str, ctx: Context) -> LoginStatus:
    """Finish a paste-mode Globus login with the one-time authorization code the user pasted (from
    the page Globus showed after they approved). Single-use and short-lived — not a password, not a
    token. Only needed when authenticate()/connect_facility reported login_mode="paste"."""
    return await login_gate._complete_login(ctx.request_context.lifespan_context, code)
  ```

<details><summary>note</summary>

```
   1: # V1 release
   2: 
   3: > [!abstract] In one line
   4: > The sprint plan for publishing hpc-bridge V1 — **scoped to what's built and tested**: the SSH-bootstrap path + zero-SSH MEP for consent-free facilities + BYO discovery, shipped to a **Claude Code plugin marketplace**. Decided 2026-08-21 (maintainer + Ryan, after Ryan's live MEP testing). This note is the plan of record — if a task runs long, come back here to reorient.
   5: 
   6: ## The three decisions (2026-08-21)
   7: 
   8: 1. **Scope — the "honest V1":** V1 supports the **SSH-bootstrap path** (curated + BYO-discovered facilities) and **zero-SSH facility-MEP dispatch for consent-free facilities** (the [[Endpoint reuse and MEP integration|M1 path]], validated live on globus1). Shipped examples: Anvil (SSH) + globus1 (MEP). **Explicitly deferred to V1.x:** M2 (the Globus browser-consent flow — required for consent-gated facility MEPs), MFA-bootstrap facilities ([#3](https://github.com/ryanchard/hpc-bridge/issues/3): NERSC/ALCF/OLCF/TACC), the ACCESS catalog channel ([#7](https://github.com/ryanchard/hpc-bridge/issues/7)), customizable resources ([#2](https://github.com/ryanchard/hpc-bridge/issues/2)). *This supersedes the earlier "V1 = M1 + M2" framing in [[Endpoint reuse and MEP integration]] — M2 was never exercisable on globus1 (consent-free), and gating V1 on it gates V1 on a facility we don't have.*
   9: 2. **The long-task block-thrashing bug gets FIXED before V1** (not documented-around). Symptom (seen 2026-08-19 under cluster contention): a compute block is CANCELLED at 24–142 s repeatedly before a 180 s task completes, orphaning the `poll_task` handle — the agent polls forever. Pre-existing, SSH path, the [[Cost control]]/#21 area (block keep-alive vs the Parsl scaling strategy). Fix on its own branch after M1 merges.
  10: 3. **Distribution = a Claude Code plugin marketplace** — installable from the terminal (`/plugin` flow), not just `--plugin-dir`. Defines the Tier-3 work.
  11: 
  12: ## The tiers (work backwards from "published")
  13: 
  14: **Tier 1 — merge PR #41 (`feat/mep-m1`)** ✅ *(done 2026-09-03)*
  15: - [x] General code review of the branch diff — done 2026-08-21 (independent reviewer on `src/` + maintainer pass on harness/docs): no merge-blockers; 4 should-fix (MEP account dropped on the startup-pin path; `$USER`-remainder scratch roots broke the session-shell env fingerprint; an offline MEP read as "allocating nodes…"; `stop_mep` drained a *running* task's handle) + 4 nits, **all fixed with tests** (commit `fix(review)`)
  16: - [x] Clean green regression re-run on a quiet cluster — **all green**: wave 1 3/3 (`mep_compute_only`, `happy_path`, `endpoint_reuse_chain`, 2026-08-19); `endpoint_reuse`, `facility_cache`, `session_persistence` (08-19); `spend_gate_enforced`, `gated_provision`, `long_task_via_handle` (2026-09-01, once a node freed). The only red left in wave 2 was the `spend_refusal` grader gap (Tier 2).
  17: - [x] Address review findings → un-draft → squash-merge #41 — **merged 2026-09-03** (`main` @ `45547b6`, branch deleted). **Tier 1 complete.**
  18: 
  19: **Tier 2 — V1 quality**
  20: - [ ] ~~Fix the long-task block-thrashing bug~~ → **re-scoped 2026-09-03 after root-cause: it was a HARNESS artifact, not a product bug.** Two concurrent `run_suite` invocations both allocated pool user `test-00` (per-process allocator, no cross-process claim) and one run's user-wide `scancel -u` teardown killed the other's live blocks (timestamps match to the second; the exact `sacct` signature — `CANCELLED by <pool uid>`, `None assigned` — was reproduced live with a pending dummy job + the verbatim teardown). Two items replace it:
  21:   - [x] **Harness:** cross-process pool claims (`harness/pool.py`, flock), **run-scoped teardown** (delete only this run's endpoint; cancel only its `uep.<eid>` blocks — never `-u`), endpoint-log capture into every bundle, a manual `sweep_pool_user.sh` for stranded leftovers — PR `fix/harness-pool-isolation`.
  22:   - [x] **Product (the surviving observation):** after the other run deleted its *endpoint*, `poll_task` hung for 20+ min. Now a pending task whose endpoint is offline/gone is reported as a terminal `failed` (ORPHANED) and its handle dropped (`_endpoint_gone` / `_orphaned_outcome`, PR `fix/poll-task-lost-endpoint`); a killed block under a live endpoint still reads `running` (Parsl relaunches it — polling is correct). **Live-checked 2026-09-03** on a real endpoint (globus1, pool user, no agent): long task → external `gce stop` → poll → `failed` ORPHANED. ✅
  23: - [ ] **New-user story** — re-scoped 2026-09-03 into two product features (the index is meant as a PUBLIC registry; the Globus login should be in-terminal like the Cloudflare plugin's):
  24:   - [x] **B. In-terminal Globus login** — **merged 2026-09-03 (PR #48)**: `needs_login` phase + `authenticate`/`complete_login`, the Compute SDK's own UserApp/client id/storage, loopback browser flow that **waits and continues in the same call**, paste-back fallback, minimum consent. L1–L5 ✅ (L5 = the fresh-user walk: login + MEP attach in one 7 s call). Plan + findings: [[In-terminal Globus login]].
  25:   - [x] **A. Public registry** — **merged 2026-09-03 (PR #49)**: [x] index id baked in (`PUBLIC_REGISTRY_INDEX`; env overrides) · [x] anonymous reads · [x] `list_facilities` out of the box · [x] **registry wins over the local BYO cache for any catalogued id** (decision 2026-09-03; a stale SSH-era `globus1` cache would have shadowed the MEP entry) · [x] "add your facility" recipe (README + [[Facility catalog]]) · [x] **no-account on a MEP = terminal + sticky, live-verified 2026-09-03** (driver + agent-level; details in [[Endpoint reuse and MEP integration]]). **Still open:** a purpose-named production index (today's is `hpc-bridge-test`) and the curator of record · MEP-facility survey DONE → [[MEP facilities survey]] (documented MEPs: ALCF Polaris/Crux, NCSA Delta, NeSI Mahuika; Anvil live-but-undocumented; per-facility template keys are a model gap before any is added).
  26:   - [x] **Then the stranger's walk** — **merged 2026-09-03 (PR #50)**: fresh state → `needs_login` → browser → `list_facilities` → connect → run; fix what's rough; this shapes the docs. **Findings, all fixed:** (1) `list_facilities` works with zero config (default registry, anonymous), but the summaries didn't say how you get in → `access`/`access_note`/`scheduler` on `CatalogSummary` + skill/command guidance to tell the user what a facility needs before choosing; (2) the fresh-user script injected the registry id (hiding a default-index bug) → stripped; (3) a deep state dir broke every SSH with `ControlPath too long` (ssh expands `%C` to 40 hex and caps the whole socket path) → short fallback dir; (4) a newcomer with no SSH access got `hpc-bridge error: RuntimeError: seed storage.db (mkdir) failed: u@h: Permission denied…` → `NO SSH ACCESS to <host> as <user>` (+ where the name came from, the remedies, nothing started) and `CANNOT REACH <host>`; (5) the MEP attach notice's "NO account is needed" (allocation) collided with the new identity refusal → "NO allocation account". Live-proven with a fresh Google Globus identity against Anvil (SSH refused) and globus1 (identity refused). **Agent-level walk PASSED 2026-09-03** (`scripts/fresh_user_session.sh --reset`, zero config): list with access notes (~14 s) → "connect me to globus1" attached in one call (~30 s) → block warm on `main` in ~2 min → `hostname` on `globus2` (aarch64, 20 cores) → stop reported draining honestly (no cancel channel, ~600 s idle tail). Three narration slips traced to our text and fixed: the agent inferred access from a clean attach (attach is identity-blind — the notice and skill now say so), promised a login node/allocation list for a MEP (the `access_note` now says connect only attaches), and read `session_spend: 0` as free (status now says no charge factor is configured, not a free tier).
  27: - [ ] **Fake-cluster tier** — the Docker spike is **PROVEN + merged (PR #46, `agentic/fakecluster/`)**: a real bootstrap → compute block → run → confirmed stop ran in 96 s with zero product changes. To make it a tier: **~½ day** — env knobs in `run_smoke.sh`/`run_suite.py` (test host, docker network), extend pool users to `-09`, run `happy_path` + the cheap cost-safety scenarios against it; **~1 day** — target-parametrised scenario facts + the chaos scenarios only it can run deterministically (kill a block under `poll_task`, saturate-then-release). Unblocks live checks whenever globus1 is busy.
  28: - [ ] **End-user docs** — *in progress (2026-09-03, `docs/user/`)*: install + quickstart, the supported-facility matrix (Anvil · globus1-MEP · BYO), platform notes (local provisioning Linux-only; BYO/MEP cross-platform)
  29: - [ ] `spend_refusal` grader accepts proactive refusal (small, agentic-only)
  30: - [x] **Agentic coverage for the new-user story + a model sweep** (merged #51; cheap tier swept twice — round 2: 29/30, Haiku's one failure = not calling the deferred tool; block tier pending) (branch `feat/agentic-stranger-scenarios`, 2026-09-03): six scenarios — `zero_config_list`, `needs_login_paste`, `mep_no_account`, `no_ssh_access`, `registry_over_cache`, `stranger_mep_walk` — with harness knobs (`NO_GLOBUS_DB`, `GLOBUS_DB_SECRET`, server-only `EXTRA_ENV`, `SEED_FACILITY_CACHE`, `SERIAL`) and graders that read the agent's words (`Trace.texts`). Sweep plan: Opus 5 / Sonnet 5 / Haiku 4.5, cheap tier first (no cluster blocks), block tier serial; subscription-billed. Recipe in `agentic/README.md`.
  31:   - *Status at the 2026-09-03 vault audit:* **PR #51 open** — round 1 of the sweep run and written up (`Reference/Model sweep 2026-09-03.md` on that branch); it also carries two product fixes (`TRANSIENT_CONFLICT_LIMIT`; the probe path's `NO SSH ACCESS` explanation) and a `COOLDOWN_S` knob (`no_ssh_access` is a fail2ban trigger — serial, 660 s apart).
  32: 
  33: **Tier 3 — release engineering**
  34: - [ ] Marketplace packaging + publish (`.claude-plugin/plugin.json` versioning, the marketplace entry, install-from-terminal verified)
  35: - [ ] `0.1.0 → 1.0.0`, tag, changelog
  36: - [ ] Security review (SSH + credential handling — run the security-review pass over the repo)
  37: - [ ] Docs hygiene: absorb/retire the 5 leftover `docs/design/*.md` into the vault; final vault reconcile
  38: 
  39: ## Standing decisions that shape the work
  40: - MEP entries are **compute-only** (no login shape) with **draining-only stop** — settled in M1, don't relitigate.
  41: - MEP config comes from the **Globus index, never the SSH probe** ([[Discovery channel model]]).
  42: - Open question parked with the cluster admin: drop `interface` from the MEP seed so the facility template owns the NIC (safer; not V1-blocking).
  43: 
  44: ## Where things stand
  45: Live state, gotchas, and how-to-run: `HANDOFF.md` (repo root). M1 design: [[Endpoint reuse and MEP integration]]. The regression harness: `agentic/README.md`.
```
</details>


# ITEM 22

## ep:Reference/The MCP tools.md|2026-09-23T00:56:28Z|sha256:083a7|src/hpc_bridge/server.py#run_shell
**episode** · note `Reference/The MCP tools.md` · seq 11 · commit f7e2fbc2 · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#run_shell` run_shell — **signature**  (note lines [24])
  ```
  was: @mcp.tool()
async def run_shell(
    command: str, ctx: Context, session_id: str = "default", shape: str = "slurm"
) -> ShellOutcome:
    """Run a shell command on the warm HPC compute block.

    `shape` picks the execution target on the same endpoint: "slurm" runs on a
    scheduler block (heavy compute, billed, idle-released); "login" runs on the login
    node via a LocalProvider (lightweight, no allocation). Sessions (cwd/env) persist
    per session_id within a shape."""
    try:
        return await _run_shell(
            ctx.request_context.lifespan_context, command, session_id, shape
  ---
  now: @mcp.tool()
async def run_shell(
    command: str, ctx: Context, session_id: str = "default", shape: str = DEFAULT_SHAPE
) -> ShellOutcome:
    """Run a shell command on the warm HPC compute block.

    `shape` picks the execution target on the same endpoint: "compute" runs on a
    scheduler block (heavy compute, billed, idle-released); "login" runs on the login
    node via a LocalProvider (lightweight, no allocation). Sessions (cwd/env) persist
    per session_id within a shape."""
    try:
        return await _run_shell(
            ctx.request_context.lifespan_context, command, session_i
  ```

<details><summary>note</summary>

```
   1: # The MCP tools
   2: 
   3: > [!abstract] Role
   4: > The agent-facing surface — **seven** tools, all declared in [[server]], all returning structured [[models|Pydantic results]] (failures come back as outcomes, never raw crashes).
   5: 
   6: ## Stand up & run
   7: 
   8: | Tool | Returns | What it does |
   9: |---|---|---|
  10: | `ensure_endpoint_up(shape="slurm", partition=None, confirm_spend=False, account=None)` | `EndpointStatus` | Provision/probe the endpoint; reports `up` only once a **worker answers a canary** ([[Warmth, the canary & cold-start]]), else `provisioning`. A billed `slurm` block won't start without `confirm_spend=True` → `needs_confirmation`. `partition` and `account` (the chosen allocation) select the Slurm target and persist for the session. |
  11: | `run_shell(command, session_id="default", shape="slurm")` | `ShellOutcome` | Run a command on the warm block (`shape="slurm"`) or the login node (`shape="login"`, free — the no-SSH discovery channel). Cold endpoint → `cold_start` (no hang). cwd/env persist per session ([[Session continuity]]). |
  12: | `reset_session(session_id="default")` | `ShellOutcome` | Clear a session's persisted cwd + environment. |
  13: | `stop_endpoint()` | `EndpointStatus` | Release the billed Slurm block over the login endpoint (AMQP, no SSH); **leave the login-node endpoint online** for a zero-SSH reconnect. "Stop" = stop spending, not tear down ([[Cost control]]). Retries a cold release channel to confirm; `status="down"` = cancel confirmed, `status="draining"` = dispatched but **unconfirmed** (re-call to confirm; #24). |
  14: | `login_shell(command)` | `LoginShellResult` | Read-only command on the login node over a **fresh SSH** connection — the cold-start discovery escape hatch. Prefer `run_shell(shape="login")` once an endpoint is up ([[Discovery today]]). SSH facility only. |
  15: 
  16: ## Catalog selection (the agentic discovery front)
  17: 
  18: | Tool | Returns | What it does |
  19: |---|---|---|
  20: | `list_facilities(query="")` | `list[CatalogSummary]` | Browse the [[Facility catalog]] (the Globus Search index). Agent-safe summaries — identity + provenance, **no** executable config or raw UUIDs. No SSH, no spend. |
  21: | `connect_facility(facility, ssh_host=None, details=None)` | `ConnectFacilityResult` | Bind a machine and bring up its **free login shape** (SSH cold-bootstrap once, or reuse an online endpoint — no Slurm account needed), run the facility's allocation command over Compute, return `needs_account`. `provisioning` ⇒ still warming. **Not in the catalog ⇒ discover, don't interrogate:** pass `ssh_host` and the tool **probes the login node**, returning `proposed_facility_details` with a draft [[models\|FacilityDetails]] to confirm with the user; call again with `details=…` to register a **session-local** entry (never indexed) and proceed (the login-shape canary validates it). With neither ⇒ `needs_facility_details` (asks for the host). See [[Globus index discovery channel]]. |
  22: 
  23: > [!note] Two execution channels
  24: > `run_shell`/`reset_session` ride [[Two-channel architecture|AMQP]] (the warm block or the login shape). `login_shell` is the only tool that opens a fresh SSH — reserved for cold-start discovery.
  25: 
  26: > [!note] The selection flow
  27: > `list_facilities` → `connect_facility(facility)` → pick an allocation → `ensure_endpoint_up(account=…, partition=…, confirm_spend=True)`. Machine + allocation are **agent-chosen at runtime** ([[Facility catalog]]); a machine can also be pinned at startup with `HPC_BRIDGE_MACHINE`.
  28: 
  29: ## See also
  30: [[server]] · [[models]] · [[Facility catalog]] · [[Resource shapes & the spend floor]] · [[Discovery today]]
```
</details>


# ITEM 23

## ep:Planned/In-terminal Globus login.md|2026-09-23T01:00:40Z|sha256:a519f|src/hpc_bridge/server.py#complete_login
**episode** · note `Planned/In-terminal Globus login.md` · seq 48 · commit 05d2f8c6 · state broken

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#complete_login` complete_login — **body**  (note lines [24, 29, 36, 41, 52])
  ```
  was: @mcp.tool()
async def complete_login(code: str, ctx: Context) -> LoginStatus:
    """Finish a paste-mode Globus login with the one-time authorization code the user pasted (from
    the page Globus showed after they approved). Single-use and short-lived — not a password, not a
    token. Only needed when authenticate()/connect_facility reported login_mode="paste"."""
    return await _complete_login(ctx.request_context.lifespan_context, code)
  ---
  now: @mcp.tool()
async def complete_login(code: str, ctx: Context) -> LoginStatus:
    """Finish a paste-mode Globus login with the one-time authorization code the user pasted (from
    the page Globus showed after they approved). Single-use and short-lived — not a password, not a
    token. Only needed when authenticate()/connect_facility reported login_mode="paste"."""
    return await login_gate._complete_login(ctx.request_context.lifespan_context, code)
  ```

<details><summary>note</summary>

```
   1: # In-terminal Globus login
   2: 
   3: > [!abstract] In one line
   4: > Replace the manual prerequisite (`globus-compute-endpoint login` in a terminal, before first use) with a **Cloudflare-shaped OAuth login that the agent surfaces and the browser completes** — a `needs_login` phase carrying an authorize URL; the browser redirects back to a loopback listener inside the server and the session continues; paste-back as the fallback. One consent covers every scope hpc-bridge needs. It rides the **Compute SDK's own `UserApp`** (same client id, same `storage.db`) so endpoint credential seeding keeps working unchanged. Tier-2 item B of [[V1 release]]; the same mechanism later carries a MEP's consent (M2).
   5: 
   6: > [!success] Built and merged — 2026-09-03, [PR #48](https://github.com/ryanchard/hpc-bridge/issues/48)
   7: > This note is the design record and its live findings. The implementation is documented as ground truth in [[login]] (`LoginFlow`, the wait-and-continue, `globus_identity_label`) and [[login_flow_manager]] (the quiet loopback manager, paste-back); the tools and phases in [[The MCP tools]] / [[models]]; the gate's position in [[server]]. `HPC_BRIDGE_LOGIN_WAIT_S` in [[Configuration]].
   8: 
   9: ## Why
  10: 
  11: A stranger's first run today: hpc-bridge needs a Globus login carrying `openid` + `manage_projects` + refresh tokens ([[Credential seeding]]); a plain SDK login isn't enough; the MCP server **cannot prompt** (stdio), so `credentials.MissingCredentials` surfaces as a generic `failed` telling the user to go run a CLI command elsewhere and come back. That is the single worst moment of the new-user experience — and it's the exact problem the Cloudflare MCP solved with `authenticate` / `complete_authentication`.
  12: 
  13: ## Verified facts this rests on (2026-09-03)
  14: 
  15: - **globus-sdk 4.8 ships the flow.** `GlobusAppConfig(login_flow_manager="local-server")` → `LocalServerLoginFlowManager`: opens the browser, runs a loopback HTTP server on an **ephemeral `localhost` port**, receives the auth code on redirect, exchanges it, returns tokens — the terminal continues. `"command-line"` is the paste-back variant (Globus shows a one-time code page). `_check_remote_session()` refuses the local-server flow in SSH/headless sessions — the natural switch to paste-back.
  16: - **The client id is pinned — and must be.** The Compute SDK builds `UserApp(client_id=DEFAULT_CLIENT_ID …)` (`4cf29807-…`); an override requires id **and** secret (a *confidential* client — a different thing). The remote `globus-compute-endpoint` refreshes tokens with **that** client id, so any token the endpoint must refresh has to be issued to it. ⟹ hpc-bridge drives the **same** `UserApp` (same client, same `storage.db` at `GLOBUS_COMPUTE_USER_DIR`), only choosing the login-flow manager. **Registering our own OAuth client (the Cloudflare way) would break seeding — don't.**
  17: - **Localhost redirect for that client:** an unauthenticated fetch of the authorize URL with `redirect_uri=http://localhost:8642/` rendered Globus's normal login page (HTTP 200), identical to the control with the client's known redirect — no up-front rejection. Suggestive, not conclusive (Globus may re-validate at consent). **The definitive check is one real login (~10 s) once built**; if it fails, the code falls back to paste-back automatically.
  18: - **Anonymous registry reads** ([[Facility catalog]]): Search "requires authentication only for non-public entries" — so the *registry* does **not** need login. Login is needed only to **dispatch** (Compute) and to **start an endpoint** (`manage_projects`). Consequence: `list_facilities` never triggers login; `connect_facility` does, lazily, at first need.
  19: 
  20: ## Design
  21: 
  22: **Phase, not prompt.** `connect_facility` checks, before any SSH, whether the Compute app is logged in with adequate scopes (`app.login_required()` against the required scope set, plus the seeding adequacy check `credentials` already does). If not, it returns **`phase="needs_login"`** with:
  23: - `login_url` — the Globus authorize URL (PKCE, `refresh_tokens=True`, all scopes below);
  24: - `login_mode` — `"browser"` (a loopback listener is waiting; completing the login in the browser finishes it) or `"paste"` (remote/headless: Globus will show a code; hand it to `complete_login`);
  25: - a `notice` telling the agent exactly what to say: show the link, wait for the user, call `connect_facility` again. **The agent never sees or handles a token**; in browser mode it never sees the code either (browser → `localhost` → server).
  26: 
  27: **Tools.**
  28: - `authenticate()` — explicit trigger: (re)starts the flow and returns the same `{login_url, login_mode}`; for "log me in first" or an expired URL.
  29: - `complete_login(code)` — paste-back only: exchanges a one-time auth code (not a token) for tokens into the Compute `storage.db`. Mirrors Cloudflare's `complete_authentication`.
  30: - `connect_facility` re-called after login proceeds as today (probe / bootstrap / seeding all unchanged).
  31: 
  32: **Minimum consent (implemented, verified live 2026-09-03):** exactly the endpoint floor the Compute SDK's own `globus-compute-endpoint login` asks for — Compute (`…facd7ccc…/all`) + Auth `openid` + `manage_projects` (`globus_compute_endpoint/auth.py:get_globus_app_with_scopes`), requested through the SDK's OWN `UserApp` / client id / `storage.db` so the remote endpoint can refresh what we stored. **Search is NOT requested:** the registry is public, so `list_facilities` and catalog reads are anonymous (`SearchClient()` without an app — see [[Globus index discovery channel]]); a Search scope only ever enters via the curator CLI (`hpc-bridge-catalog`). One consent screen; refresh tokens make later runs silent. *Why the login may bounce through UChicago / ACCESS:* Globus is a federation broker — a facility's high-assurance / session policy demands a *recent* authentication of the linked identity, so Globus redirects to that IdP. That is Globus's rule, not a scope of ours (the same URL logs a user with no such policy in with Globus alone).
  33: 
  34: **The listener.** Bound to `127.0.0.1` only, ephemeral port, single-use `state`, PKCE, **10-minute lifetime** then it stops and the URL is dead (a fresh `needs_login` re-arms it — idempotent). Runs as a background thread in the server process; completing the login writes tokens via the SDK's own token storage. It exists only between `needs_login` and the next call.
  35: 
  36: **Fallbacks (implemented).** Browser mode is armed only when a graphical browser is available on this machine — a pre-flight `webbrowser.get()` against the SDK's text-browser deny list; `SSH_TTY`/`SSH_CONNECTION` ⇒ paste — because the SDK only discovers 'no browser' *after* producing the URL. A browser attempt that dies (no browser, Globus rejected the redirect) is remembered, so the next `authenticate` goes straight to paste; `authenticate(mode="paste")` forces it; a flow whose URL was never produced falls back to paste in-call. Paste-back = Globus's auth-code page: the user hands the one-time code to `complete_login(code)` — never a password, and the code is stored via the SDK's *validating* storage (same unchanging-identity check a browser login gets). 10-min TTL: an expired attempt can't be completed, and a stale worker from an earlier attempt can't touch a re-armed flow (per-attempt generation). The login gate runs **first** in `connect_facility` — before the catalog read (whose SDK `Client` would otherwise run its own command-line login on the MCP transport) and before any SSH.
  37: 
  38: **Wait-and-continue (added after the first fresh-user test, 2026-09-03).** The first design returned `needs_login` the instant the listener was armed and left the agent to ask the user to 'say when done'. Live, with a Globus web session and this client's consent already in the browser, the redirect landed **4 s** after the URL was issued — the login was over before the agent finished writing its message, the user then re-opened the single-use link (the loopback had already closed) and read the failure as 'it's reusing the token'. Now the tool call that arms a browser flow **waits for it** (`LoginFlow.wait`, up to `HPC_BRIDGE_LOGIN_WAIT_S` = 90 s — a real IdP round-trip fits; well under the 10-min TTL and any MCP tool timeout, which `run_shell` already exceeds routinely) and, when it lands, **continues the connection in the same call** — the Cloudflare-plugin feel the design was after. A browser attempt that fails during the wait is re-armed in paste mode at once. Only a still-open (slow) login returns `needs_login`, and its notice says how long it waited, that a finished page means 'just call again', and that the link is single-use. The listener lives in the MCP server process: quitting the session mid-login kills it (the tokens already stored survive).
  39: 
  40: ## What the agent is taught (`skills/driving-hpc/SKILL.md` — [[Plugin packaging]])
  41: On `needs_login`: present `login_url` as a link and say what will happen ("your browser will log you in to Globus; when it says you can return, tell me"); then call `connect_facility` again. In paste mode: ask the user to paste the code Globus shows and call `complete_login(code)`. **Never** ask for a Globus password; never paste a URL into a shell. Same discipline as `needs_preauth`.
  42: 
  43: ## Not in scope / later
  44: - M2: a facility MEP's consent-required 401 becomes a `needs_login` with the consent URL — same phase, same tools.
  45: - Multiple Globus identities / choosing an identity: the Globus login page handles it.
  46: - ~~Logout / re-login (`force`): `authenticate(force=True)` is a natural extension; not V1.~~ *Superseded: `authenticate(force=True)` shipped in the same PR (it re-arms a login even when one is present), and `authenticate(mode="paste")` forces paste mode. A new login also drops the sticky MEP no-account verdicts and rebuilds the runners (`_forget_identity_verdicts`, [[server]]).*
  47: 
  48: ## Milestones
  49: | L | Deliverable |
  50: |---|---|
  51: | **L1** | ✅ **built** (`login.py`, `login_flow_manager.py`, `server.py`) — detection at connect → `needs_login` + `login_url`/`login_mode`; loopback browser flow; `authenticate(force)` |
  52: | **L2** | ✅ **built** — `complete_login(code)`; paste mode chosen for remote/headless sessions or when the browser flow can't produce a URL |
  53: | **L3** | ✅ **built** — SKILL.md + `hpc-connect.md` guidance; models; 12 hermetic tests (a start()/worker-thread lock deadlock in the fallback path was found by them and fixed) |
  54: | **L4** | ✅ **PASSED 2026-09-03** — scratch token dir → `needs_login` (browser) → login + one consent → Globus redirected to the loopback on `127.0.0.1` → `done` → `login_required()` False → all three resource servers stored with the required scopes **and refresh tokens**. **Globus honours the `localhost` redirect for the Compute client — confirmed.** Follow-up found by the check: the SDK's redirect handler logs the request line (with the one-time code) to stderr — silenced in our manager subclass. |
  55: | L5 fresh-user walk | ✅ 2026-09-03 |
  56: 
  57: ## See also
  58: [[login]] · [[login_flow_manager]] · [[V1 release]] · [[Credential seeding]] · [[Facility catalog]] · [[Endpoint reuse and MEP integration]] (M2) · [[MFA and interactive SSH auth]] (the `needs_preauth` precedent) · [[credentials]]
```
</details>


# ITEM 24

## ep:Modules/endpoint.md|2026-09-23T00:56:03Z|sha256:a4159|src/hpc_bridge/endpoint.py#EndpointCLI
**episode** · note `Modules/endpoint.md` · seq 51 · commit 957ccedb · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/endpoint.py#EndpointCLI` EndpointCLI — **body**  (note lines [4, 8, 9, 10, 11, 14])
  ```
  was: class EndpointCLI:
    def __init__(self, user_dir: Path | None = None, runner: Runner | None = None) -> None:
        self.user_dir = user_dir
        self._run = runner or self._default_run

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.user_dir is not None:
            env["GLOBUS_COMPUTE_USER_DIR"] = str(self.user_dir)
        return env

    def _ep_dir(self, name: str) -> Path:
        base = self.user_dir or (Path.home() / ".globus_compute")
        return base / name

    def config_path(self, name: str) -> Path:
        return self._ep_dir(name) 
  ---
  now: class EndpointCLI:
    def __init__(self, user_dir: Path | None = None, runner: Runner | None = None) -> None:
        self.user_dir = user_dir
        self._run = runner or self._default_run

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.user_dir is not None:
            env["GLOBUS_COMPUTE_USER_DIR"] = str(self.user_dir)
        return env

    def _ep_dir(self, name: str) -> Path:
        base = self.user_dir or (Path.home() / ".globus_compute")
        return base / name

    def user_template_path(self, name: str) -> Path:
        # globus-compute-en
  ```
- `src/hpc_bridge/endpoint.py#EndpointCLI` EndpointCLI.configure — **unchanged** EndpointCLI changed elsewhere (body); EndpointCLI.configure unchanged (note lines [4, 8, 9, 10, 11, 14])
  ```
  was: async def configure(self, name: str, multi_user: bool = False) -> None:
        # hpc-bridge invariant: always a PERSONAL (single-user) endpoint, never a MEP.
        # globus-compute-endpoint's default auto-selects multi-user from the configuring
        # user's POSIX capabilities, which can silently create a multi-user (identity-
        # mapping) endpoint — the exact thing this project avoids. Force it off.
        rc, _out, err = await self._run(
            "configure", "--multi-user", "true" if multi_user else "false", name
        )
        if rc != 0:
            raise RuntimeError(f
  ---
  now: async def configure(self, name: str, multi_user: bool = False) -> None:
        # hpc-bridge invariant: always a PERSONAL (single-user) endpoint, never a MEP.
        # globus-compute-endpoint's default auto-selects multi-user from the configuring
        # user's POSIX capabilities, which can silently create a multi-user (identity-
        # mapping) endpoint — the exact thing this project avoids. Force it off.
        rc, _out, err = await self._run(
            "configure", "--multi-user", "true" if multi_user else "false", name
        )
        if rc != 0:
            raise RuntimeError(f
  ```
- `src/hpc_bridge/endpoint.py#EndpointCLI` EndpointCLI.start — **unchanged** EndpointCLI changed elsewhere (body); EndpointCLI.start unchanged (note lines [4, 8, 9, 10, 11, 14])
  ```
  was: async def start(self, name: str) -> str:
        # 4.x `start` runs in the FOREGROUND by default; --detach daemonizes it and
        # returns promptly. The registered UUID is written to endpoint.json, not stdout.
        rc, _out, err = await self._run("start", name, "--detach")
        if rc != 0:
            raise RuntimeError(f"start failed: {err}")
        return self.endpoint_id(name)
  ---
  now: async def start(self, name: str) -> str:
        # 4.x `start` runs in the FOREGROUND by default; --detach daemonizes it and
        # returns promptly. The registered UUID is written to endpoint.json, not stdout.
        rc, _out, err = await self._run("start", name, "--detach")
        if rc != 0:
            raise RuntimeError(f"start failed: {err}")
        return self.endpoint_id(name)
  ```
- `src/hpc_bridge/endpoint.py#EndpointCLI` EndpointCLI.stop — **unchanged** EndpointCLI changed elsewhere (body); EndpointCLI.stop unchanged (note lines [4, 8, 9, 10, 11, 14])
  ```
  was: async def stop(self, name: str) -> None:
        rc, _out, err = await self._run("stop", name)
        if rc != 0:
            raise RuntimeError(f"stop failed: {err}")
  ---
  now: async def stop(self, name: str) -> None:
        rc, _out, err = await self._run("stop", name)
        if rc != 0:
            raise RuntimeError(f"stop failed: {err}")
  ```
- `src/hpc_bridge/endpoint.py#EndpointCLI` EndpointCLI.config_path — **removed**  (note lines [4, 8, 9, 10, 11, 14])
  ```
  was: def config_path(self, name: str) -> Path:
        return self._ep_dir(name) / "config.yaml"
  ---
  now: 
  ```
- `src/hpc_bridge/endpoint.py#EndpointCLI` EndpointCLI.user_template_path — **unchanged** EndpointCLI changed elsewhere (body); EndpointCLI.user_template_path unchanged (note lines [4, 8, 9, 10, 11, 14])
  ```
  was: def user_template_path(self, name: str) -> Path:
        # globus-compute-endpoint 4.x runs `start` as an EndpointManager whose
        # config.yaml must be engine-free; the compute engine lives here, in the
        # per-user-process (UEP) template.
        return self._ep_dir(name) / "user_config_template.yaml.j2"
  ---
  now: def user_template_path(self, name: str) -> Path:
        # globus-compute-endpoint 4.x runs `start` as an EndpointManager whose
        # config.yaml must be engine-free; the compute engine lives here, in the
        # per-user-process (UEP) template.
        return self._ep_dir(name) / "user_config_template.yaml.j2"
  ```
- `src/hpc_bridge/endpoint.py#EndpointCLI` EndpointCLI._default_run — **unchanged** EndpointCLI changed elsewhere (body); EndpointCLI._default_run unchanged (note lines [4, 8, 9, 10, 11, 14])
  ```
  was: async def _default_run(self, *args: str) -> tuple[int, str, str]:
        if sys.platform != "linux":
            raise RuntimeError(
                f"globus-compute-endpoint runs only on Linux (this host is {sys.platform!r}); "
                "it cannot provision a local endpoint here. Set HPC_BRIDGE_ENDPOINT_ID=<uuid> "
                "to dispatch to an existing endpoint, or run hpc-bridge on Linux "
                "(container/WSL/HPC login node)."
            )
        proc = await asyncio.create_subprocess_exec(
            "globus-compute-endpoint",
            *args,
            stdo
  ---
  now: async def _default_run(self, *args: str) -> tuple[int, str, str]:
        if sys.platform != "linux":
            raise RuntimeError(
                f"globus-compute-endpoint runs only on Linux (this host is {sys.platform!r}); "
                "it cannot provision a local endpoint here. Set HPC_BRIDGE_ENDPOINT_ID=<uuid> "
                "to dispatch to an existing endpoint, or run hpc-bridge on Linux "
                "(container/WSL/HPC login node)."
            )
        proc = await asyncio.create_subprocess_exec(
            "globus-compute-endpoint",
            *args,
            stdo
  ```

<details><summary>note</summary>

```
   1: # endpoint.py
   2: 
   3: > [!abstract] Role
   4: > `EndpointCLI` — drives the **local** `globus-compute-endpoint` binary (configure / start / stop) for [[facility-local]]. The local counterpart of [[facility-remote]]'s `RemoteEndpointCLI`.
   5: 
   6: ## What it does
   7: 
   8: - **`configure(name)`** (`endpoint.py:58`) — runs `configure --multi-user false` (always personal, never an identity-mapping MEP).
   9: - **`start(name)`** (`:69`) — `start --detach` (4.x `start` is foreground by default), then reads the registered UUID from `endpoint.json`.
  10: - **`stop(name)`** (`:77`).
  11: - **Path helpers** — `config_path` (the engine-free manager config) and `user_template_path` (`:31`, where the engine lives — the v4 invariant).
  12: 
  13: > [!warning] Linux-only, fail-loud
  14: > `_default_run` (`:40`) raises a clear error on non-Linux hosts: `globus-compute-endpoint` can't provision locally there — set `HPC_BRIDGE_ENDPOINT_ID` to dispatch to an existing endpoint, or run on Linux. (macOS dev uses BYO.)
  15: 
  16: ## See also
  17: [[facility-local]] · [[Two-channel architecture]] · [[Configuration]]
```
</details>


# ITEM 25

## ep:Concepts/MEP & templated endpoints.md|2026-09-23T00:56:19Z|sha256:1b862|src/hpc_bridge/facility/remote.py#SlurmFacility
**episode** · note `Concepts/MEP & templated endpoints.md` · seq 9 · commit afc540d4 · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/facility/remote.py#SlurmFacility` SlurmFacility.config_template — **unchanged** SlurmFacility changed elsewhere (body); SlurmFacility.config_template unchanged (note lines [29, 30])
  ```
  was: def config_template(self, hpc: Profile) -> tuple[str, dict]:
        """Return (jinja_template_str, default_user_opts) for the UEP template.

        ONE template serves every shape: provider.type and resources are Jinja
        variables rendered per task from user_endpoint_config (see shapes.py). Defaults
        come from the MachineProfile so a bare submit still resolves. min_blocks is
        always 0 (+ max_idletime) so an idle slurm block self-releases — the cost net,
        validated live on Anvil. LocalProvider ignores the slurm keys.

        Profile defaults are injected as json.du
  ---
  now: def config_template(self, hpc: Profile) -> tuple[str, dict]:
        """Return (jinja_template_str, default_user_opts) for the UEP template.

        ONE template serves every shape: provider.type and resources are Jinja
        variables rendered per task from user_endpoint_config (see shapes.py). Defaults
        come from the MachineProfile so a bare submit still resolves. min_blocks is
        always 0 (+ max_idletime) so an idle slurm block self-releases — the cost net,
        validated live on Anvil. LocalProvider ignores the slurm keys.

        Profile defaults are injected as json.du
  ```
- `src/hpc_bridge/facility/remote.py#SlurmFacility` SlurmFacility.provision — **body**  (note lines [29, 30])
  ```
  was: async def provision(self, hpc: Profile) -> EndpointHandle:
        # Idempotent: reuse a running endpoint; configure only if it doesn't exist yet
        # (re-configuring an existing one raises ConfigExists).
        name = self.profile.endpoint_name
        st = await self.cli.status(name)
        if st == "running":
            # REUSE: we did NOT launch it, so its node is unknown from a fresh
            # round-robin probe — leave login_host None and keep any prior record.
            return EndpointHandle(endpoint_id=await self.cli.endpoint_id(name), name=name)
        if st is None:
   
  ---
  now: async def provision(self, hpc: Profile) -> EndpointHandle:
        # Idempotent: reuse a running endpoint; configure only if it doesn't exist yet
        # (re-configuring an existing one raises ConfigExists).
        name = self.profile.endpoint_name
        st = await self.cli.status(name)
        if st == "running":
            # REUSE: we did NOT launch it, so its node is unknown from a fresh
            # round-robin probe — leave login_host None and keep any prior record.
            return EndpointHandle(endpoint_id=await self.cli.endpoint_id(name), name=name, reused=True)
        if st
  ```

<details><summary>note</summary>

```
   1: # MEP & templated endpoints
   2: 
   3: > [!abstract] In one line
   4: > One endpoint = a **manager daemon** on the login node plus a **Jinja config template** rendered *per task* into a User Endpoint Process; that UEP's Parsl provider `sbatch`s a block and runs the work on a compute node.
   5: 
   6: ## What it is
   7: 
   8: The endpoint is a Globus Compute **v4 Multi-User Endpoint (MEP)** run in *personal / single-user* mode. "Multi-user" here names the **manager + templated-UEP** architecture — *not* identity mapping:
   9: 
  10: - **Manager** — a detached daemon on one login node. Its `config.yaml` is **engine-free** (just `display_name`, `amqp_port`). It registers with Globus and listens on AMQP.
  11: - **UEP (User Endpoint Process)** — forked by the manager *per task*. Its engine + provider come from `user_config_template.yaml.j2`, rendered from the `user_endpoint_config` dict the task carries.
  12: - **Block → compute node** — the UEP's Parsl provider (`SlurmProvider` / `LocalProvider`) submits a scheduler block; a Parsl worker starts on the compute node and connects back over the high-speed `interface` (see [[Two-channel architecture]]).
  13: 
  14: ```mermaid
  15: flowchart TD
  16:   T["task + user_endpoint_config"] --> M["Manager daemon<br/>config.yaml (engine-free)"]
  17:   M -- "fork + render template" --> U["UEP<br/>user_config_template.yaml.j2"]
  18:   U -- "SlurmProvider.sbatch" --> B[Slurm block]
  19:   B --> W[Parsl worker on compute node]
  20:   U -. "LocalProvider → login node<br/>(shape=login)" .-> L[Login-node worker]
  21: ```
  22: 
  23: ## Shapes: one endpoint, many configs
  24: 
  25: `user_endpoint_config` is a named bag of template vars — a **shape** ([[shapes]]). `shape="slurm"` renders a `SlurmProvider` (billed compute block); `shape="login"` renders a `LocalProvider` (a free process on the login node — also the no-SSH discovery channel). See [[Resource shapes & the spend floor]].
  26: 
  27: ## How it shows up in the code
  28: 
  29: - The template + default vars: `SlurmFacility.config_template()` ([[facility-remote]], `remote.py:450`).
  30: - The manager + UEP config written at provision: `provision()` (`remote.py:585`).
  31: - The shape → vars mapping: `shape_config()` ([[shapes]]).
  32: 
  33: > [!warning] `config.yaml` must be engine-free
  34: > `gce start` runs an *EndpointManager*; if the engine is in `config.yaml` it fails — the engine must live in the UEP template (the v4 manager+template model). `configure` also forces `--multi-user false`; the default auto-selects an identity-mapping MEP from POSIX capabilities.
  35: 
  36: > [!warning] Branch on the boolean `is_slurm`, never a string compare
  37: > The manager runs `user_opts` through `_sanitize_user_json`, which `json.dumps`'s every *string* (so `"SlurmProvider"` arrives as `'"SlurmProvider"'`). A template `{% if provider_type == 'SlurmProvider' %}` then silently fails and drops the whole provider block. Booleans pass through untouched, so the template branches on the `is_slurm` bool ([[shapes]]). This was a real, hard-to-see bug ([#5](https://github.com/ryanchard/hpc-bridge/issues/5)).
  38: 
  39: > [!note] `run_in_sandbox: true` — and why it's safe
  40: > The engine sets `run_in_sandbox: true`: ShellFunctions expect a sandbox, and without it every task logs *"Task sandboxing will not work due to endpoint misconfiguration."* Sandboxing runs each task in `tasks_working_dir/<TASK_UUID>` — harmless here because the [[Session continuity|session shim]] immediately `cd`s to an absolute `<scratch>/sessions/<id>` path, overriding the sandbox landing dir. The config is written at `configure` time, so a flip only takes effect on a **freshly bootstrapped** endpoint, not a reused one.
  41: 
  42: ## See also
  43: [[Resource shapes & the spend floor]] · [[shapes]] · [[facility-remote]] · [[Standing up the endpoint]] · [[Two-channel architecture]]
```
</details>


# ITEM 26

## ep:Modules/profile.md|2026-09-23T01:00:36Z|sha256:27a93|src/hpc_bridge/server.py#_apply_partition
**episode** · note `Modules/profile.md` · seq 47 · commit 524c3dc7 · state broken

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#_apply_partition` _apply_partition — **anchor-missing** symbol_not_found (note lines [8])

<details><summary>note</summary>

```
   1: # profile.py
   2: 
   3: > [!abstract] Role
   4: > The **session-level** profile: how this run behaves (interactive vs batch, block sizing, idle grace). Distinct from a facility's `MachineProfile`.
   5: 
   6: ## What it does
   7: 
   8: `Profile` (`profile.py:11`) is a frozen dataclass with three fields: `mode` (`interactive` | `batch`, from `HPC_BRIDGE_PROFILE`), `nodes_per_block` (the spend clock's node count), `max_idletime_s` (default 600 — the [[Cost control|idle-release]] grace, and the `max_idletime` written into the UEP template). It validates `mode` against `MODES` (`:7`) and rejects a sub-1s idle time. The account, partition and queue are **not** here — they are per-facility (`MachineProfile`) and per-session selections threaded into `user_endpoint_config` ([[server]] `_apply_account` / `_apply_partition`). `mode="interactive"` pre-spawns a block (`init_blocks=1`, the `@@EAGER@@` template slot); `batch` (the default) starts lazily.
   9: 
  10: > [!note] Two different "profiles"
  11: > `Profile` (here) is **session policy** and applies to any facility. `MachineProfile` ([[facility-remote]]) is **per-facility data** (host, modules, interface, …). Don't conflate them.
  12: 
  13: ## See also
  14: [[server]] · [[facility-remote]] · [[Cost control]]
```
</details>


# ITEM 27

## ep:Planned/Aurora (PBS + bastion) bring-up.md|2026-09-23T00:58:06Z|sha256:bfaad|src/hpc_bridge/facility/remote.py#SshTarget
**episode** · note `Planned/Aurora (PBS + bastion) bring-up.md` · seq 58 · commit 0691fdae · state broken

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/facility/remote.py#SshTarget` SshTarget.argv — **body**  (note lines [8])
  ```
  was: def argv(self, remote_cmd: str) -> list[str]:
        # Never-prompt (BatchMode fails fast instead of hanging on a password/MFA prompt). With an
        # explicit key we pin it (IdentitiesOnly); with none we DEFER to ~/.ssh/config's IdentityFile.
        # A pre-opened master (e.g. one Duo on an MFA facility) is reused regardless of BatchMode;
        # ControlMaster=auto opens one non-interactively on a key host.
        opts = ["ssh"]
        if self.key_path:
            opts += ["-i", self.key_path, "-o", "IdentitiesOnly=yes"]
        opts += [
            "-o", "BatchMode=yes",
         
  ---
  now: def argv(self, remote_cmd: str) -> list[str]:
        # Never-prompt (BatchMode fails fast instead of hanging on a password/MFA prompt). With an
        # explicit key we pin it (IdentitiesOnly); with none we DEFER to ~/.ssh/config's IdentityFile.
        # A pre-opened master (e.g. one Duo on an MFA facility) is reused regardless of BatchMode;
        # ControlMaster=auto opens one non-interactively on a key host.
        opts = ["ssh"]
        if self.key_path:
            opts += ["-i", self.key_path, "-o", "IdentitiesOnly=yes"]
        # Host keys: hpc-bridge trusts exactly what YOUR ssh t
  ```

<details><summary>note</summary>

```
   1: # Aurora (PBS + bastion) bring-up
   2: 
   3: > [!abstract] Status
   4: > ALCF **Aurora** — the first **PBS + bastion/MFA** facility. The SSH → bootstrap → PBS-provisioning path is proven live end-to-end; the billed compute block is gated on an **active Aurora allocation** (the test project is storage-only), so `interface=hsn0` is **validated-pending-allocation**.
   5: 
   6: ## The two-hop bastion — and why it needs no new code
   7: 
   8: Aurora is reached via `bastion.alcf.anl.gov` (a pass-through) → a login node (`aurora.alcf.anl.gov`, which round-robins to a UAN). hpc-bridge needs **no new SSH code**: `SshTarget.argv` ([[facility-remote]]) builds a plain `ssh user@host` and OpenSSH reads `~/.ssh/config`, so a `ProxyJump bastion.alcf.anl.gov` block makes the hop transparent. A fresh connection wants **two MFA passcodes** (one per hop); the [[MFA and interactive SSH auth|ControlMaster]] then multiplexes so the rest of the session never re-auths — the same "authenticate once" substrate as any MFA facility.
   9: 
  10: ## The management-hostname pin (fixed)
  11: 
  12: Aurora's `hostname -f` is `aurora-uan-0009.**hostmgmt.cm**.aurora.alcf.anl.gov` — a **management-plane** name not routable through the bastion. Pinning it would break teardown/reconnect, so `_routable_pin` ([[facility-remote]]) now drops management labels (`hostmgmt`/`cm`/`mgmt`/`ipmi`/`bmc`) and falls back to the alias ([#33](https://github.com/ryanchard/hpc-bridge/pull/33)).
  13: 
  14: ## The discovered config
  15: 
  16: | field | value | note |
  17: |---|---|---|
  18: | `scheduler` | `pbs` | |
  19: | `interface` | `hsn0` | Slingshot NIC on the UAN, on the compute fabric — **the crux**, validated-pending-allocation |
  20: | `partition` (queue) | `debug` | 1–2 nodes, 1 hr |
  21: | `scheduler_options` | `#PBS -l filesystems=home:flare` | **mandatory** — omit and the job is held; `home` for the venv, `flare` for scratch |
  22: | `scratch_root` | `/lus/flare/projects/<project>/{user}/.hpc-bridge` | **project-based** (per-user) — why Aurora isn't a clean [[Facility catalog]] entry yet (a catalog `scratch_root` is `{user}`-templated, not project-templated) |
  23: | `env_setup` | `module load python/3.12.12` → idempotent venv + `pip install globus-compute-endpoint` | login node reaches PyPI; the idempotent guard means the compute node reuses the shared `/home` venv (hence `filesystems=home`) |
  24: | `cpus_per_node` | `104` | |
  25: 
  26: ## Proven vs pending
  27: 
  28: - **Proven live** (2026-07): the two-hop MFA bootstrap, ControlMaster reuse, `globus-compute-endpoint` install on the UAN, the PBS provisioning attempt, and a clean stop (no leaked pilot). The [#32](https://github.com/ryanchard/hpc-bridge/issues/32) pilot-rejection observability was *surfaced* here — a `qsub` rejected with `No active allocation found for project … and resource aurora` now shows up in the `provisioning` notice instead of a silent "allocating nodes…".
  29: - **Pending an allocation**: the compute pilot never runs (the test project has no active Aurora compute), so `interface=hsn0` is unvalidated live — one `account=` swap + rerun when an allocation lands. If it stays cold *with* an allocation, the interface is wrong (try `hsn1`, then a `bond0`).
  30: 
  31: ## Testing it as a new user
  32: 
  33: `agentic/clean-session.sh` launches a pristine Claude Code session — no `~/.claude` priors, an **isolated** `HPC_BRIDGE_STATE_DIR` sandbox, and **nothing forced** (no `HPC_BRIDGE_SSH_HOST` override — see [#35](https://github.com/ryanchard/hpc-bridge/issues/35)) — so a cold agent drives Aurora exactly as a real user would (discover → propose → confirm), not from leaked cache.
  34: 
  35: ## See also
  36: [[facility-remote]] · [[MFA and interactive SSH auth]] · [[Standing up the endpoint]] · [[MEP & templated endpoints]] · [[Cost control]] · [[Facility catalog]]
```
</details>


# ITEM 28

## ep:Modules/server.md|2026-09-23T01:02:11Z|sha256:1fd3e|src/hpc_bridge/connect.py#_connect_mep
**episode** · note `Modules/server.md` · seq 66 · commit 7f16fff4 · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/connect.py#_connect_mep` _connect_mep — **body**  (note lines [13, 33])
  ```
  was: async def _connect_mep(app: AppCtx, facility: str, fac) -> ConnectFacilityResult:
    """Bind a facility-run multi-user endpoint (MEP). Called under app.lock, after the bind.

    There is nothing to stand up: the facility runs the manager and its identity mapping makes our
    Globus identity a local account — zero SSH. So we only ATTACH the catalogued UUID (free) and
    read the manager's status. We deliberately do NOT warm a block here: on a MEP every shape is a
    billed scheduler block, so warming belongs behind the spend gate (ensure_endpoint_up
    confirm_spend=True), not inside conn
  ---
  now: async def _connect_mep(app: AppCtx, facility: str, fac) -> ConnectFacilityResult:
    """Bind a facility-run multi-user endpoint (MEP). Called under app.lock, after the bind.

    There is nothing to stand up: the facility runs the manager and its identity mapping makes our
    Globus identity a local account — zero SSH. So we only ATTACH the catalogued UUID (free) and
    read the manager's status. We deliberately do NOT warm a block here: on a MEP every shape is a
    billed scheduler block, so warming belongs behind the spend gate (ensure_endpoint_up
    confirm_spend=True), not inside conn
  ```

<details><summary>note</summary>

```
   1: # server.py
   2: 
   3: > [!abstract] Role
   4: > The FastMCP server — the agent-facing entry point. Declares the **eleven** MCP tools, holds session state (`AppCtx`), gates on the Globus login, selects/binds the facility (SSH personal endpoint or facility MEP), and runs the provision → canary → dispatch → spend flow under a lock.
   5: 
   6: ## What it does
   7: 
   8: `server.py` is the runtime heart. It exposes eleven tools ([[The MCP tools]]), each a thin `@mcp.tool()` wrapper over a private `_`-helper that takes the `AppCtx`:
   9: 
  10: | Tool | Helper | Does |
  11: |---|---|---|
  12: | `list_facilities` | `_list_facilities` | browse the public registry ([[Facility catalog]]) — anonymous, agent-safe summaries with `access`/`access_note` |
  13: | `connect_facility` | `_connect_facility` | **login gate first**, then resolve (details → registry → cache → probe) and bind: bring up the login shape + list allocations (SSH), or attach with zero SSH (`_connect_mep`) |
  14: | `authenticate` | `_authenticate` | the Globus login gate as a tool: arm a login (browser loopback / paste), wait, report `LoginStatus` |
  15: | `complete_login` | `_complete_login` | finish a paste-mode login with the one-time auth code |
  16: | `ensure_endpoint_up` | `_ensure_endpoint_up` | provision/probe; report warm via the canary; thread account/partition; surface pilot state, dispatch failures, the terminal NO ACCOUNT |
  17: | `run_shell` | `_run_shell` | dispatch a command to the warm block / login shape; hand back a poll handle past the sync-wait |
  18: | `poll_task` | `_poll_task` | retrieve a long task's result; ORPHANED when its endpoint is gone |
  19: | `reset_session` | `_reset_session` | clear a session's cwd/env |
  20: | `stop_endpoint` | `_stop_endpoint` / `_stop_mep` | release the block over AMQP and leave the manager online (SSH), or drain honestly (MEP) |
  21: | `teardown_endpoint` | `_teardown_endpoint` | fully destroy the endpoint (`gce stop` + delete over SSH) — or, on a MEP, detach |
  22: | `login_shell` | `_login_shell` | read-only login-node command over SSH (cold-start escape hatch); refused on a MEP |
  23: 
  24: (Helpers carry the logic; the `@mcp.tool()` wrappers are thin. Exact line numbers drift — grep the symbol.)
  25: 
  26: ## How it works
  27: 
  28: - **State.** `AppCtx` (`:85`) holds the facility, profile, endpoint state, the per-shape `ShapeRuntime` (`:44` — its Executor, canary result, spend clock, the sticky `no_account` verdict, `spend_confirmed`), the live `TaskHandle`s (`:71`), the session-local facilities dict, the `LoginFlow` ([[login]]), and an `asyncio.Lock`. `lifespan` (`:423`) builds it from `make_facility` + env and installs the real `LoginFlow`.
  29: - **The Globus login gate.** `_connect_facility` (`:1115`) checks `login_flow.login_required()` **before the catalog read and before any SSH** — every non-`unsupported` outcome needs Globus, and constructing the SDK `Client` for the catalog on a fresh install would run the SDK's *own* command-line login on the MCP transport. `_start_login_and_wait` (`:1313`) arms the flow and, in browser mode, **waits** `_login_wait_s()` (`:1306`, `HPC_BRIDGE_LOGIN_WAIT_S` = 90 s) for the redirect to land — then the connect simply continues; a browser attempt that fails during the wait is re-armed in paste mode. Otherwise `_needs_login_result` (`:1355`) returns `phase="needs_login"` with the URL and the agent-facing instructions (`_login_notice`, `:1327`: relay the link, single-use, never a password). `_authenticate` (`:989`) / `_complete_login` (`:1004`) are the same flow as tools; both call `_forget_identity_verdicts` (`:1856`) on success — a new login may be a different identity, so sticky no-account verdicts are dropped and runners rebuilt.
  30: - **Facility selection.** `make_facility` (`:315`) returns a facility resolved from the [[Facility catalog|registry]] (`HPC_BRIDGE_MACHINE`, via `_catalog_facility` `:282`) or a `LocalFacility`. `_facility_from_entry` (`:248`) is the shared seam: a `compute_mep_uuid` entry → `MEPFacility` ([[facility-mep]]) — **MEP wins**; else `profile_from_catalog_entry` + `_slurm_facility` (`:203`), which reads the login-node pin from [[state]] and rebinds the CLI to it. `make_catalog` (`:373`) reads the registry with a **built-in** id (`PUBLIC_REGISTRY_INDEX`; `HPC_BRIDGE_SEARCH_INDEX` overrides) through `_make_search_client` (`:345`) — **anonymous** unless the Compute identity already holds the Search scope; it never triggers a login. `lifespan` **boots resiliently** — a failed `make_facility` (stale env, no registry) warns and starts unbound rather than crashing; `connect_facility` then binds and **moves `scratch_root`** to the facility (`_resolve_scratch_root`, `:331`, [[Session continuity]]). `HPC_BRIDGE_SSH_HOST` overrides the SSH host **only on this startup-pin path** (`_facility_from_entry(pinned_host=…)`); the agentic `connect_facility` path uses the *bound* facility's own `ssh_host`, so a global env can't silently redirect an agent-chosen facility ([#35](https://github.com/ryanchard/hpc-bridge/issues/35)).
  31: - **Resolution precedence in `_connect_facility`.** An explicit `details=` is a (re)definition and overrides everything (and is cached to `facilities.json` via `_facility_store`, `:1063`); else a session-local entry; else **the registry** (`make_catalog().get`); else the local BYO cache (`FacilityStore`, keyed on `ssh_host` — only for ids the registry doesn't know, or when it is unreachable); else `_propose_or_ask` (`:1394`). The registry wins for any catalogued id (decision 2026-09-03, [#49](https://github.com/ryanchard/hpc-bridge/issues/49): a stale SSH-era `globus1` cache would have shadowed the MEP entry).
  32: - **Un-indexed discovery.** `_propose_or_ask` builds a bare `SshTarget` (SSH user from `_ssh_config_user` / `ssh -G`, `:118`; key + host from `~/.ssh/config` + env) and runs the [[discovery]] probe → `proposed_facility_details`, or `needs_preauth` (`_needs_preauth_result`, `:1366`, carrying `preauth_command` — [[MFA and interactive SSH auth]]). On confirm, `_entry_from_details` (`:1071`) builds a session-local entry whose endpoint name comes from `_session_endpoint_name` (`:1052`) — `hpc-bridge-<ssh_host slug>`, keyed on the SSH host (`HPC_BRIDGE_ENDPOINT_NAME` overrides it for harness run isolation). `_control_settings` (`:136`) configures the shared ControlMaster ([[facility-remote]]), with `_short_control_dir` (`:161`) keeping the socket path under the Unix cap.
  33: - **Two kinds of bind.** After the bind, `_connect_facility` asks `_has_login_shape` (`:485`, from `_supported_shapes` `:475` — `getattr(facility, "supported_shapes", SHAPES)`). With a login shape it provisions `login`, then runs the allocation command over Compute → `needs_account`; a bootstrap SSH failure is rewritten by `_explain_provision_error` (`:170`) into `NO SSH ACCESS to <host> as <user>` / `CANNOT REACH <host>` ([[Standing up the endpoint]]). Without one — a facility MEP — `_connect_mep` (`:1258`) only **attaches** (reads the manager's status; an OFFLINE manager is a `failed` naming the facility as owner) and returns `needs_account` with `reused=True`, saying whether an account is needed (`account_required`) and that attaching does *not* test the identity mapping. `_shape_reject` (`:489`) then refuses the `login` shape at every entry point (`ensure_endpoint_up`, `run_shell`, `reset_session`, `login_shell`) before a `ShapeRuntime` exists.
  34: - **The provision choke point.** `_provision` (`:725`): the spend floor → bootstrap if there's no endpoint → `ensure_warm` ([[lifecycle]]) → on `"warm"`, confirm a *live worker* via `_confirm_worker` (`:593`, the canary) → `_settle_billing`. Both `ensure_endpoint_up` and `run_shell` (via `_ensure_warm_runner`, `:1936`) reach it. A non-timeout canary failure marks the runner stale (`runner_stale`, rebuilt by `_runner_for` `:570`) and keeps the failed `CanaryResult`; `_dispatch_error_suffix` (`:1837`) puts its text on the `provisioning` notice, labelling a 409 `RESOURCE_CONFLICT` as TRANSIENT (`_transient_dispatch_failure`, `:1849`).
  35: - **The terminal NO ACCOUNT ([[facility-mep]]).** `_no_account_failure` (`:1877`) matches the MEP manager's identity-mapping refusals (`_NO_ACCOUNT_MARKERS`, `:1870`); `_confirm_worker` records the verdict on `ShapeRuntime.no_account` (**sticky** — later calls return without re-submitting), and `_ensure_endpoint_up` returns a terminal `down` / `_cold_outcome` (`:1905`) a terminal `failed` whose `_no_account_notice` (`:1891`) names the identity — from the error itself (`_identity_from_error`, `:1885`) or `globus_identity_label` ([[login]]) — and says what unblocks it. Cleared by a re-bind, teardown, or a new login.
  36: - **The lock.** Serialises provision / runner-swap / stop so concurrent tool calls can't race `AppCtx`. Dispatch happens *outside* the lock, so a long command doesn't serialise everything else. `_stop_endpoint` (`:1680`) cancels the block over the login shape (AMQP) via `_release_blocks_over_login` (`:1497`; `scancel` on Slurm, `qdel` on PBS, matched by the `uep.<eid>` marker), then drops the billed shape (`_drop_compute_shape`, `:1614`) — leaving the manager online for reuse; unconfirmed ⇒ `draining` ([#24](https://github.com/ryanchard/hpc-bridge/issues/24)). On a MEP `_stop_mep` (`:1633`) is **draining-only and terminal** (no cancel channel; refuses while a task still runs), and `_teardown_endpoint` (`:1725`) is a **detach** ([[Cost control]]). The runner `close()` is non-blocking ([[runner]]) so a stop returns promptly.
  37: - **Long-task poll handles ([#21](https://github.com/ryanchard/hpc-bridge/issues/21)).** A command that outlives the sync-wait is registered in `AppCtx.tasks` (`_register_task`, `:1971`) and returned as `phase="running"`; `_poll_task` (`:2123`) reaps it via `_resolve_task` (`:1999`). A live task short-circuits the warmth [[Warmth, the canary & cold-start|canary]], blocks a same-session second dispatch (`_busy_session`, `:1949`) **and** a partition/account change (both would corrupt or cancel it), and every block-close site drains the registry (`_drain_shape_tasks`, `:560`). A pending task whose endpoint is unbound or reports offline is **ORPHANED** — `_endpoint_gone` (`:2097`) / `_orphaned_outcome` (`:2110`): a terminal `failed`, handle dropped, instead of `running` forever ([#44](https://github.com/ryanchard/hpc-bridge/issues/44); a killed block under a *live* endpoint still reads `running` — Parsl relaunches it).
  38: - **The spend floor.** `_provision` returns `"needs_confirmation"` for a billed (`compute`) shape until `confirm_spend=True` — see [[Resource shapes & the spend floor]]. Partition/account selection is threaded in via `_apply_partition` (`:761`) / `_apply_account` (`:787`) after `_VALID_PARTITION`/`_VALID_ACCOUNT` (`:757`) validate the token. `_needs_confirmation_notice` (`:808`) names the free login shape as the alternative only where one exists.
  39: - **Pilot-state observability ([#32](https://github.com/ryanchard/hpc-bridge/issues/32)).** When a billed block stays cold, `_ensure_endpoint_up` (`:826`) enriches the `provisioning` notice with the pilot's ACTUAL scheduler state — read over the login shape (AMQP) by the same `uep.<eid>` marker the release path uses (`_pilot_status_over_login`, `:1589`; `_augment_provisioning_notice`, `:1601`): `RUNNING`/queued/`HELD`, or, past a ~45 s grace (`PROVISION_GRACE_S`, clocked by `ShapeRuntime.provisioning_since`), *"no pilot → likely REJECTED"*. Otherwise a rejected/held `qsub` (bad account, missing `filesystems` directive) is indistinguishable from a normal queue wait — surfaced live on [[Aurora (PBS + bastion) bring-up|Aurora]]. Skipped on a MEP (no login shape); there, "provisioning with no canary ever recorded" means the manager reported OFFLINE, and the notice says so. A warm billed block's notice also carries `_billed_bounds_note` (`:698`) and, with no charge factor configured, says `session_spend: 0` is not a free tier.
  40: 
  41: > [!warning] "warm" means a *worker* answered — not "manager online"
  42: > `manager_online` (a cheap web query) only reflects the login-node manager. In the MEP model the first task forks the UEP and submits the block, so the manager reads online while the next command would cold-start. `_confirm_worker` submits a **canary** through the real Executor; only a returned result ⇒ warm. `CANARY_TTL_S` (`:460`) then trusts that for 45 s so an interactive burst doesn't pay the round-trip each call. See [[Warmth, the canary & cold-start]].
  43: 
  44: > [!warning] The login gate must run before the SDK `Client` is built
  45: > `_make_search_client` uses `Client(do_version_check=False)` and `app.login_required()` (non-prompting) precisely because the SDK's version check is an *authenticated* call: on a fresh install it would trigger the SDK's command-line login — a URL on stdout and `input()` on stdin, i.e. the MCP transport (found in the [#48](https://github.com/ryanchard/hpc-bridge/issues/48) review). Keep the gate first in `_connect_facility`.
  46: 
  47: > [!note] In flight (PR [#51](https://github.com/ryanchard/hpc-bridge/issues/51), open)
  48: > Two product changes ride the agentic-scenarios PR: `TRANSIENT_CONFLICT_LIMIT` (three consecutive `RESOURCE_CONFLICT` refusals ⇒ a `down` saying another session with the same identity holds the endpoint — a model sweep showed an agent retrying 7×), and `_propose_or_ask` routing a refused probe SSH through `_explain_provision_error`. On `main` the transient hint repeats and the probe path returns the raw text.
  49: 
  50: ## See also
  51: [[Two-channel architecture]] · [[Warmth, the canary & cold-start]] · [[Resource shapes & the spend floor]] · [[The MCP tools]] · [[login]] · [[facility-mep]] · [[runner]] · [[lifecycle]] · [[facility-remote]] · [[Facility catalog]] · [[Configuration]]
  52: 
  53: > [!note] Split in progress (2026-09-03)
  54: > Step 1 moved the runtime data types (`AppCtx`, `ShapeRuntime`, `TaskHandle`, `DEFAULT_SHAPE`) to [[context]]; `server` re-exports them. The plan and the remaining steps are in [[Review 2026-09-03 — code quality]] §1.
  55: > Step 2 moved the env reads (as typed accessors), the runtime tunables and the ControlMaster settings to [[config]].
  56: > Steps 3–4 moved every pure notice/outcome builder to [[notices]] and the spend clock to [[cost]]; the shape-capability reads (`_supported_shapes`, `_has_login_shape`, `_idle_release_s`) went to [[context]] and the task-ceiling maths (`_parse_hhmmss`, `_task_ceiling_s`) to [[config]]. `server.py` is now ~1810 lines (from 2276).
  57: > Step 5 moved facility/catalog construction to [[binding]] — callers use module attributes; tests patch `binding.*` / `config._control_settings`. `server.py` ≈ 1550 lines.
  58: > Step 6 moved the scheduler ops (block release, pilot status) to [[scheduler_ops]] with the login-shape runner injected (`_login_runner`).
  59: > Steps 7–8 moved the warmth state machine and task-handle bookkeeping to [[warmth]]; tests patch `warmth._provision` / `warmth._drop_compute_shape`.
  60: > Step 9 moved the login gate (`_start_login_and_wait`, `_authenticate`, `_complete_login`) to [[login_gate]].
  61: > Step 10 moved the connect flow to [[connect]] (injected login-shape runner; `server._connect_facility` is a thin wrapper). **Split complete:** `server.py` holds the FastMCP app, `lifespan`, the tool wrappers and the orchestration seams (`_ensure_endpoint_up`, `_run_shell`, `_reset_session`, `_poll_task`, `_stop_*`, `_teardown_endpoint`, `_login_shell`) — ≈820 lines, from 2276 before the split. **NB:** the function-location notes in the body of this page predate the split; the per-module pages ([[context]], [[config]], [[notices]], [[cost]], [[binding]], [[scheduler_ops]], [[warmth]], [[login_gate]], [[connect]]) are authoritative for where a function lives now.
```
</details>


# ITEM 29

## ep:Concepts/Standing up the endpoint.md|2026-09-23T00:56:31Z|sha256:7c5fd|src/hpc_bridge/state.py#LoginNodeStore
**episode** · note `Concepts/Standing up the endpoint.md` · seq 10 · commit 875de8c0 · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/state.py#LoginNodeStore` LoginNodeStore — **body**  (note lines [30])
  ```
  was: class LoginNodeStore:
    def __init__(self, path: Path | str | None = None) -> None:
        default = Path.home() / ".hpc-bridge" / "endpoints.json"
        self.path = Path(path) if path else default

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # write 0600 from creation: open with rest
  ---
  now: class LoginNodeStore:
    def __init__(self, path: Path | str | None = None) -> None:
        default = _state_dir() / "endpoints.json"
        self.path = Path(path) if path else default

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # write 0600 from creation: open with restrictive mode, t
  ```

<details><summary>note</summary>

```
   1: # Standing up the endpoint
   2: 
   3: > [!abstract] In one line
   4: > First connect: **reuse an already-online endpoint over the web (zero SSH)**, else SSH once to seed credentials, write the manager + UEP config, `start` the daemon detached, and **pin** the login node it landed on.
   5: 
   6: ## The flow
   7: 
   8: `SlurmFacility.bootstrap()` ([[facility-remote]], `remote.py:544`) is the entry, and it is **reuse-or-SSH**:
   9: 
  10: ```mermaid
  11: flowchart TD
  12:   A[bootstrap] --> B{find_online_endpoint<br/>web query}
  13:   B -- "online endpoint we own" --> R["reuse over AMQP<br/>(ZERO SSH)"]
  14:   B -- none --> C{whoami over SSH<br/>creds usable?}
  15:   C -- no --> S[seed trimmed storage.db]
  16:   C -- yes --> P
  17:   S --> P[provision]
  18:   P --> P1[configure --multi-user false]
  19:   P1 --> P2["write engine-free config.yaml<br/>+ UEP template"]
  20:   P2 --> P3[start --detach]
  21:   P3 --> P4[capture FQDN + pin login node]
  22: ```
  23: 
  24: - **Reuse first** (`find_online_endpoint`, `remote.py:643`) — a still-running endpoint from a prior session is reused over AMQP with no SSH. This is the [[Two-channel architecture|SSH-once]] keystone, and the reattach is now **surfaced** on the connect result (`ConnectFacilityResult.reused`) instead of being silent ([#20](https://github.com/ryanchard/hpc-bridge/issues/20)).
  25: - **Credentials** — seeded only if the remote can't already authenticate (`whoami`). See [[Credential seeding]].
  26: - **Provision** (`remote.py:585`) — `configure` (forced `--multi-user false`) → write the engine-free manager `config.yaml` + the [[MEP & templated endpoints|UEP template]] → `start --detach`.
  27: - **Pin** — record the login node so the next session reconnects directly ([[state]]).
  28: 
  29: > [!warning] Login-node pinning
  30: > The manager lives on ONE login node, but the SSH alias round-robins. `start` (`remote.py:315`) captures the FQDN *in the same SSH connection* that launches the daemon — a separate `hostname -f` could resolve a different node and orphan the manager on teardown. The FQDN is stored by [[state]]'s `LoginNodeStore`; the CLI `rebind`s there next session.
  31: 
  32: > [!note] Idempotent
  33: > Bootstrap reuses a running endpoint, seeds credentials only when absent, and re-writes config on every provision so the current profile always applies.
  34: 
  35: ## See also
  36: [[Two-channel architecture]] · [[Credential seeding]] · [[MEP & templated endpoints]] · [[facility-remote]] · [[state]] · [[Discovery today]]
```
</details>


# ITEM 30

## ep:Modules/facility-base.md|2026-09-23T00:56:03Z|sha256:cda6b|src/hpc_bridge/facility/base.py#EndpointHandle
**episode** · note `Modules/facility-base.md` · seq 9 · commit afc540d4 · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/facility/base.py#EndpointHandle` EndpointHandle — **body**  (note lines [9])
  ```
  was: @dataclass(frozen=True)
class EndpointHandle:
    endpoint_id: str
    name: str
    login_host: str | None = None  # resolved FQDN the manager daemon landed on
  ---
  now: @dataclass(frozen=True)
class EndpointHandle:
    endpoint_id: str
    name: str
    login_host: str | None = None  # resolved FQDN the manager daemon landed on
    reused: bool = False  # attached to an already-online endpoint (no fresh provision, no SSH)
  ```
- `src/hpc_bridge/facility/base.py#EndpointHandle` EndpointHandle.endpoint_id — **unchanged** EndpointHandle changed elsewhere (body); EndpointHandle.endpoint_id unchanged (note lines [9])
  ```
  was: endpoint_id: str
  ---
  now: endpoint_id: str
  ```
- `src/hpc_bridge/facility/base.py#EndpointHandle` EndpointHandle.name — **unchanged** EndpointHandle changed elsewhere (body); EndpointHandle.name unchanged (note lines [9])
  ```
  was: name: str
  ---
  now: name: str
  ```
- `src/hpc_bridge/facility/base.py#EndpointHandle` EndpointHandle.login_host — **unchanged** EndpointHandle changed elsewhere (body); EndpointHandle.login_host unchanged (note lines [9])
  ```
  was: login_host: str | None = None
  ---
  now: login_host: str | None = None
  ```

<details><summary>note</summary>

```
   1: # facility-base.py — `facility/base.py`
   2: 
   3: > [!abstract] Role
   4: > The **Facility seam**: one Protocol behind which all machine-specific behaviour lives, so the runtime is facility-agnostic.
   5: 
   6: ## What it does
   7: 
   8: - **`Facility`** Protocol (`facility/base.py:17`) — the contract the runtime depends on: `provision(profile)`, `manager_online(endpoint_id)`, `config_template(profile)`. (Concrete facilities also add `bootstrap`/`teardown`/`login_exec`/etc., accessed via `getattr` so they're optional.)
   9: - **`EndpointHandle`** (`:10`) — `provision`/`bootstrap` return value: `endpoint_id`, `name`, `login_host` (the pinned FQDN), `reused` (True if reused over the web, no SSH).
  10: 
  11: Implementations: [[facility-local]] (LocalProvider, no SSH) and [[facility-remote]] (Slurm over SSH). [[server]]'s `make_facility` picks one from env.
  12: 
  13: > [!note] Why a seam
  14: > Everything that differs between machines sits behind this Protocol; the dispatch/session/cost runtime never imports a specific facility. The discovery work ([[Discovery today]]) is about *generating* these instead of hand-writing them.
  15: 
  16: ## See also
  17: [[facility-local]] · [[facility-remote]] · [[server]] · [[Discovery today]]
```
</details>


# ITEM 31

## ep:Concepts/Resource shapes & the spend floor.md|2026-09-23T01:00:33Z|sha256:51d85|src/hpc_bridge/server.py#_needs_confirmation_notice
**episode** · note `Concepts/Resource shapes & the spend floor.md` · seq 39 · commit 426ff71d · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#_needs_confirmation_notice` _needs_confirmation_notice — **body**  (note lines [18])
  ```
  was: def _needs_confirmation_notice(app: AppCtx, where: str) -> str:
    """The spend-floor notice. Names the free login shape as the alternative ONLY where one exists —
    on a compute-only facility every shape is billed, so pointing at shape='login' is a dead-end."""
    head = (f"scheduler compute block{where} ({app.profile.nodes_per_block} node(s)): spend "
            "not yet confirmed. ")
    if _has_login_shape(app):
        return head + (
            "Surface the allocation balance (e.g. run_shell('mybalance', shape='login')) and re-call "
            "ensure_endpoint_up(confirm_spend=Tr
  ---
  now: def _needs_confirmation_notice(app: AppCtx, where: str) -> str:
    """The spend-floor notice. Names the free login shape as the alternative ONLY where one exists —
    on a compute-only facility every shape is billed, so pointing at shape='login' is a dead-end."""
    head = (f"scheduler compute block{where} ({app.profile.nodes_per_block} node(s)): spend "
            "not yet confirmed. ")
    return head + _spend_floor_guidance(app)
  ```

<details><summary>note</summary>

```
   1: # Resource shapes & the spend floor
   2: 
   3: > [!abstract] In one line
   4: > One templatable endpoint serves two **shapes** — `login` (a free `LocalProvider` on the login node) and `compute` (a billed scheduler block, `SlurmProvider` or `PBSProProvider`) — and a billed block **will not start** until spend is explicitly confirmed.
   5: 
   6: ## Shapes
   7: 
   8: A *shape* is a named bag of template vars (`user_endpoint_config`) that renders the [[MEP & templated endpoints|UEP template]]. `shape_config()` ([[shapes]]) defines them:
   9: 
  10: | Shape | Provider | Cost | Used for |
  11: |---|---|---|---|
  12: | `login` | `LocalProvider` (login node) | free, no allocation | discovery, light work, the no-SSH probe |
  13: | `compute` | `SlurmProvider` / `PBSProProvider` (scheduler block) | billed, idle-released | real compute |
  14: 
  15: Each shape has its own [[server|`ShapeRuntime`]] — its own Executor, canary, and spend clock — so they warm and bill independently. `run_shell(command, shape=...)` / `ensure_endpoint_up(shape=...)` pick the target. The `compute` block's scheduler (Slurm or PBS) is the **facility's**, not the shape's — `profile.scheduler` selects the provider/launcher template ([[facility-remote]]).
  16: 
  17: > [!warning] Compute-only facilities — `supported_shapes`
  18: > A facility multi-user endpoint ([[facility-mep]]) declares `supported_shapes = ("compute",)`; the server reads it via `_supported_shapes` and **`_shape_reject` runs before any `ShapeRuntime` is built** at every shape entry point (`ensure_endpoint_up`, `run_shell`, `reset_session`, and `login_shell`), because a submit the facility's schema refuses would shut the SDK Executor down. No login shape also means: every shape is billed (the `needs_confirmation` notice no longer points at a free `login` alternative — `_needs_confirmation_notice`), discovery runs on the warm compute block, and stop is draining-only ([[Cost control]]).
  19: 
  20: > [!warning] `compute` is a boolean, not a string
  21: > `shape_config` sets `compute: True/False`; the template branches on that bool. It must *not* compare a string like `provider_type == "SlurmProvider"`, because the manager's `_sanitize_user_json` JSON-quotes every string and the comparison silently fails — dropping the provider block ([#5](https://github.com/ryanchard/hpc-bridge/issues/5)). See [[MEP & templated endpoints]].
  22: 
  23: ## The spend floor
  24: 
  25: A billed `compute` shape returns `needs_confirmation` and **starts nothing** until `ensure_endpoint_up(confirm_spend=True)` — a deterministic gate enforced in `_provision` ([[server]], `server.py:725`). It covers `run_shell` too (its canary would otherwise kick a block). The `login` shape is free and exempt. The chosen `partition` and `account` are threaded in per task via `_apply_partition` (`server.py:761`) / `_apply_account` (`:787`) and persist for the session; both are refused while a task is still running on the shape (the runner swap would cancel it).
  26: 
  27: This is the front-end half of [[Cost control]] — the idle-release net catches the *back* end.
  28: 
  29: ## See also
  30: [[shapes]] · [[MEP & templated endpoints]] · [[facility-mep]] · [[Cost control]] · [[server]] · [[cost]]
```
</details>


# ITEM 32

## ep:Modules/server.md|2026-09-23T00:57:44Z|sha256:125a4|src/hpc_bridge/server.py#_ensure_endpoint_up
**episode** · note `Modules/server.md` · seq 20 · commit 98084692 · state changed

**Q:** Given the code change, is any claim in this note now wrong?

- `src/hpc_bridge/server.py#_ensure_endpoint_up` _ensure_endpoint_up — **body**  (note lines [14])
  ```
  was: async def _ensure_endpoint_up(
    app: AppCtx,
    shape: str = DEFAULT_SHAPE,
    partition: str | None = None,
    confirm_spend: bool = False,
    account: str | None = None,
) -> EndpointStatus:
    if partition is not None and not _VALID_PARTITION.match(partition):
        return EndpointStatus(
            status="down",
            block_state="cold",
            endpoint_id=app.state.endpoint_id,
            notice=f"invalid partition {partition!r}: must match [A-Za-z0-9_.:-]{{1,64}}",
        )
    if account is not None and not _VALID_ACCOUNT.match(account):
        return EndpointS
  ---
  now: async def _ensure_endpoint_up(
    app: AppCtx,
    shape: str = DEFAULT_SHAPE,
    partition: str | None = None,
    confirm_spend: bool = False,
    account: str | None = None,
) -> EndpointStatus:
    if partition is not None and not _VALID_PARTITION.match(partition):
        return EndpointStatus(
            status="down",
            block_state="cold",
            endpoint_id=app.state.endpoint_id,
            notice=f"invalid partition {partition!r}: must match [A-Za-z0-9_.:-]{{1,64}}",
        )
    if account is not None and not _VALID_ACCOUNT.match(account):
        return EndpointS
  ```

<details><summary>note</summary>

```
   1: # server.py
   2: 
   3: > [!abstract] Role
   4: > The FastMCP server — the agent-facing entry point. Declares the nine MCP tools, holds session state (`AppCtx`), selects the facility, and runs the provision → canary → dispatch → spend flow under a lock.
   5: 
   6: ## What it does
   7: 
   8: `server.py` is the runtime heart. It exposes nine tools ([[The MCP tools]]), each a thin `@mcp.tool()` wrapper over a private `_`-helper that takes the `AppCtx`:
   9: 
  10: | Tool | Helper | Does |
  11: |---|---|---|
  12: | `list_facilities` | `_list_facilities` | browse the [[Facility catalog\|catalog]] (agent-safe summaries) |
  13: | `connect_facility` | `_connect_facility` | bind a facility (or probe + propose an un-indexed one via `ssh_host`), bring up its login shape, list allocations |
  14: | `ensure_endpoint_up` | `_ensure_endpoint_up` | provision/probe; report warm via the canary; thread account/partition |
  15: | `run_shell` | `_run_shell` | dispatch a command to the warm block / login shape |
  16: | `poll_task` | `_poll_task` | retrieve a long task's result (the poll handle `run_shell` returns as `running`) |
  17: | `reset_session` | `_reset_session` | clear a session's cwd/env |
  18: | `stop_endpoint` | `_stop_endpoint` | release the block over AMQP; leave the manager online for reuse |
  19: | `teardown_endpoint` | `_teardown_endpoint` | fully destroy the endpoint (`gce stop` + delete over SSH) — the rare explicit case |
  20: | `login_shell` | `_login_shell` | read-only login-node command over SSH (cold-start escape hatch) |
  21: 
  22: (Helpers carry the logic; the `@mcp.tool()` wrappers are thin. Exact line numbers drift — grep the symbol.)
  23: 
  24: ## How it works
  25: 
  26: - **State.** `AppCtx` (`:61`) holds the facility, profile, endpoint state, the per-shape `ShapeRuntime` (`:42` — its Executor, canary result, and spend clock), the session-local facilities dict, and an `asyncio.Lock`. `lifespan` (`:285`) builds it from `make_facility` + env.
  27: - **Facility selection.** `make_facility` returns a `SlurmFacility` resolved from the [[Facility catalog|catalog]] (`HPC_BRIDGE_MACHINE`, or `connect_facility` at runtime — by id *or* subject) or a `LocalFacility`, reading the login-node pin from [[state]] and rebinding the CLI to it. `lifespan` **boots resiliently** — a failed `make_facility` (stale env, no index) warns and starts unbound rather than crashing; `connect_facility` then binds and **moves `scratch_root`** to the facility ([[Session continuity]]).
  28: - **Un-indexed discovery.** When `_connect_facility` (`:692`) misses the catalog, `_propose_or_ask` (`:796`) builds a bare `SshTarget` (SSH user from `_ssh_config_user` / `ssh -G`, `:87`; key + host from `~/.ssh/config` + env) and runs the [[discovery]] probe → `proposed_facility_details`. On confirm, `_entry_from_details` (`:658`) builds a session-local entry whose endpoint name comes from `_session_endpoint_name` (`:649`) — `hpc-bridge-<facility>`. `_control_settings` (`:105`) configures the shared ControlMaster ([[facility-remote]]).
  29: - **The provision choke point.** `_provision` (`:460`): bootstrap if there's no endpoint → `ensure_warm` ([[lifecycle]]) → on `"warm"`, confirm a *live worker* via `_confirm_worker` (`:364`, the canary) → `_settle_billing`. Both `ensure_endpoint_up` and `run_shell` (via `_ensure_warm_runner`) reach it.
  30: - **The lock.** Serialises provision / runner-swap / stop so concurrent tool calls can't race `AppCtx`. Dispatch happens *outside* the lock, so a long command doesn't serialise everything else. `stop_endpoint` `scancel`s the block over the login shape (AMQP) via `_release_blocks_over_login`, then drops the billed shape under the lock — leaving the manager online for reuse. The runner `close()` is non-blocking ([[runner]]) so a stop returns promptly.
  31: - **Long-task poll handles ([#21](https://github.com/ryanchard/hpc-bridge/issues/21)).** A command that outlives the sync-wait is registered in `AppCtx.tasks` (a `TaskHandle` keyed by `task_id`) and returned as `phase="running"`; `poll_task` reaps it. A live task short-circuits the warmth [[Warmth, the canary & cold-start|canary]], blocks a same-session second dispatch **and** a partition/account change (both would corrupt or cancel it), and every block-close site drains the registry.
  32: - **The spend floor.** `_provision` returns `"needs_confirmation"` for a billed (slurm) shape until `confirm_spend=True` — see [[Resource shapes & the spend floor]]. Partition selection is threaded in via `_apply_partition` (`:496`).
  33: 
  34: > [!warning] "warm" means a *worker* answered — not "manager online"
  35: > `manager_online` (a cheap web query) only reflects the login-node manager. In the MEP model the first task forks the UEP and submits the block, so the manager reads online while the next command would cold-start. `_confirm_worker` submits a **canary** through the real Executor; only a returned result ⇒ warm. `CANARY_TTL_S` (`:321`) then trusts that for 45 s so an interactive burst doesn't pay the round-trip each call. See [[Warmth, the canary & cold-start]].
  36: 
  37: ## See also
  38: [[Two-channel architecture]] · [[Warmth, the canary & cold-start]] · [[Resource shapes & the spend floor]] · [[The MCP tools]] · [[runner]] · [[lifecycle]] · [[facility-remote]]
```
</details>
