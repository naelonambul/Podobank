# Implementation Plan

## Summary

The pilots showed that host protection is the easiest step of the template to miss:

- `naelonambul/todo-cli-test` had no protection on `main` until the owner configured it partway through the first pilot.
- GitHub never copies rulesets or merge settings from a template.
- `docs/host-setup.md` says what to protect, but gives nothing to apply or check.
- The agent-identity setup (a distinct, constrained GitHub App) that made independent owner review possible is described nowhere.

This docs-only `repository` change rewrites `docs/host-setup.md`:

- a complete, import-ready ruleset for `main`, the one proven in both todo-cli-test pilots;
- the repository merge settings;
- a **read-only** check the owner or agent can run to compare a repository with that recommendation;
- an **optional** section on setting up a constrained agent identity.

It changes no behaviour. `scripts/**`, `checks.json`, `.github/**` and the change model are untouched. The template gains no helper script, and records no owner-specific identifiers such as App IDs, installation IDs or key paths.

Evidence:

- friction log: https://github.com/naelonambul/todo-cli-test/pull/2#issuecomment-5796486362 (the host-protection and App-access items);
- the todo-cli-test ruleset `main-protection`, which enforced both pilot merges (PRs naelonambul/todo-cli-test#1 and #2);
- the read-only observations of the current host state, listed below.

### Current host state (read-only, observed 2026-09-23)

| Repository | `main` protection | Merge settings |
|---|---|---|
| `todo-cli-test` | Ruleset `main-protection`: no bypass, blocks deletion and force push, one approval, dismisses stale approvals, requires approval of the last push, squash only, requires `summary` from GitHub Actions (integration 15368), strict | merge, squash and rebase all enabled at repository level. The ruleset restricts merges to squash. |
| `sdlc-project-template-v2` | Classic branch protection, not a ruleset. The App token can see that it requires `summary`; PR #2 showed a review was required. | merge, squash and rebase all enabled, with no restriction on merge method |

This change only documents the recommendation. Changing either repository's host settings is the owner's action, outside the repository and outside this change.

## Files and components that change

`write_scope`: `["docs/host-setup.md"]`

| Path | Change |
|---|---|
| `docs/host-setup.md` | Restructure and extend it as below. Keep the existing facts: squash recommended, the Free-private 403, and the trust-mode table. |

Out of scope:

- **Packet-creation interface.** This is still deferred. Choosing between a stable public command and a small scaffolding command is a separate later change. No `repo.py` internals are documented.
- Any helper script or bootstrap automation, including a scripted ruleset check under `scripts/`. The check is documented as `gh api` commands only.
- `README.md`, whose existing pointers to `docs/host-setup.md` stay correct; `AGENTS.md`, `REVIEW.md`, `changes/**` outside this packet, `scripts/**`, `.github/**`, and `checks.json`.
- Changing any live host setting.

## Content of the new `docs/host-setup.md`

Sections, in order:

1. **Intro.** Unchanged: GitHub copies no settings from a template, so configure each repository.
2. **Merge policy.**
   - Keep the existing text.
   - Add: at repository level, allow squash merging only and disable merge commits and rebase merging. The ruleset below also restricts the merge method, and the repository setting keeps the merge button consistent with it.
   - Optionally, delete head branches automatically.
3. **Protect `main` with a ruleset.** One ruleset targeting the default branch, with no bypass actors. It has these rules:

   | Rule | Setting | Why |
   |---|---|---|
   | Restrict deletions | on | |
   | Block force pushes | on | first-parent history anchors closures |
   | Require a pull request | 1 approval; dismiss stale approvals; require approval of the most recent push; squash only | a push after approval needs a fresh review, and the approver cannot be the last pusher |
   | Require status checks | `summary`, source GitHub Actions; branches must be up to date | the validated candidate is the merge candidate; pinning the source stops another integration from posting a `summary` status |

   It also includes the import-ready JSON, the exact rules proven in the pilots:

   ```json
   {
     "name": "main-protection",
     "target": "branch",
     "enforcement": "active",
     "bypass_actors": [],
     "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
     "rules": [
       {"type": "deletion"},
       {"type": "non_fast_forward"},
       {"type": "pull_request", "parameters": {
         "required_approving_review_count": 1,
         "dismiss_stale_reviews_on_push": true,
         "require_last_push_approval": true,
         "require_code_owner_review": false,
         "required_review_thread_resolution": false,
         "allowed_merge_methods": ["squash"]}},
       {"type": "required_status_checks", "parameters": {
         "strict_required_status_checks_policy": true,
         "do_not_enforce_on_create": false,
         "required_status_checks": [{"context": "summary", "integration_id": 15368}]}}
     ]
   }
   ```

   How to apply it:
   - in the UI, Settings → Rules → Rulesets → New ruleset → Import a ruleset;
   - or as the owner, `gh api -X POST repos/OWNER/REPO/rulesets --input main-protection.json`.

   Notes:
   - `15368` is the GitHub Actions app.
   - **Review modes.** A PR author cannot approve their own PR. `require_last_push_approval` requires the approval to come from someone other than whoever made the most recent reviewable push. So when a single identity both pushes and reviews, neither rule can provide a human gate. The doc states three modes explicitly, and they are not equivalent:

     | Mode | Setting | Human-review gate |
     |---|---|---|
     | **Recommended:** a separate agent identity | 1 required approval, last-push approval on, as in the JSON | Enforced. The agent identity pushes; the owner approves. |
     | Shared identity, with another authorized human reviewer | Unchanged: 1 required approval, last-push approval on | Enforced. A different authorized human reviews and approves the PR. |
     | Single person, shared identity | `required_approving_review_count: 0` | **None: this is a degraded mode.** It intentionally gives up the enforced human-approval gate. Only the required `summary` check, blocked force pushes and deletion, and the squash restriction remain enforced. Approvals are local `unverified` claims, which are not identity proof. Use it only knowingly, and record the choice in `docs/` as the trust-mode section asks. |

     The doc must not present the degraded mode as a normal alternative or as equivalent to the recommended setup.
   - Classic branch protection with the same settings is acceptable. The read-only check below cannot fully see it without administration access.
4. **Required check without enforcement.** Keep the existing text: on a Free private repository the API returns 403, CI is advisory, and the `push` run on `main` is the first authoritative gate.
5. **Read-only host check.** These commands need only read access, and work with the owner's `gh` login or a read-scoped agent token. They change nothing.

   ```sh
   gh api repos/OWNER/REPO/rules/branches/main --jq '[.[].type] | sort'
   # expect: ["deletion","non_fast_forward","pull_request","required_status_checks"]
   gh api repos/OWNER/REPO/rulesets --jq '.[] | {id, name, enforcement}'
   gh api repos/OWNER/REPO/rulesets/ID --jq '{bypass_actors, rules}'
   gh api repos/OWNER/REPO --jq '{allow_squash_merge, allow_merge_commit, allow_rebase_merge}'
   ```

   Compare the results with the ruleset above. The comparison should find:
   - `bypass_actors` empty or null;
   - `pull_request` with `allowed_merge_methods: ["squash"]`, one approval (zero only in the declared degraded mode), stale-dismissal and last-push approval on;
   - `required_status_checks` with `summary` and integration `15368`, strict;
   - repository merge settings of squash only.

   Classic protection shows in `rules/branches/main` as an empty list. Check it in the UI, or with an administration-scoped token via `repos/OWNER/REPO/branches/main/protection`.

   Run the check after creating a repository from the template, and whenever the host settings change.
6. **Trust mode.** Keep the existing two questions and the table.
7. **Optional: a constrained agent identity.** For the "distinct agent identity" row:
   - **Create a GitHub App** owned by the repository owner, with no webhook. Give it these repository permissions only:
     - Contents: read/write;
     - Pull requests: read/write;
     - Metadata, Checks and Actions: read.

     Do not grant Administration, Workflows or Secrets.
   - **Consequences of those permissions:**
     - The agent cannot change rulesets or settings.
     - GitHub rejects the agent's pushes that create or modify `.github/workflows/**`, so the owner makes workflow changes.
     - The agent cannot approve its own PR as the owner.
   - **Install** the App on selected repositories only.
   - **Private key.** Keep it outside every repository, readable only by the owner (mode 0600). Never commit, print or paste it into agent context.
   - **Tokens.** Mint short-lived installation tokens restricted to one repository and to the permissions above. Have the local helper refuse any repository not on an explicit allowlist. Tokens expire after one hour and are never stored.
   - **Commit identity.** Commit as `<app-slug>[bot]` with email `<bot-user-id>+<app-slug>[bot]@users.noreply.github.com`, so authorship shows the App.
   - **No bypass.** Never add the App as a ruleset bypass actor.
   - **Keep the helper out of the template.** The token helper is host-specific, so it lives outside the template repository. Record which identity and trust mode the project uses in `docs/`, as the trust-mode section asks.

Wording may be tightened during implementation, but must state exactly these rules.

## Order of work

1. **Plan approval (owner).** The owner approves this plan's exact digest. The agent records the claim and confirms `stage=implementation readiness=ready`.
2. **Packet commit.** Commit the packet on `change/host-setup-docs` as the `naelonambul-agent` App.
3. **Edit** `docs/host-setup.md` as specified.
4. **Check against reality.**
   - Validate the JSON block with `python3 -m json.tool`.
   - Run the documented read-only commands against `naelonambul/todo-cli-test`. The output must match the documented expectations exactly.
   - Run them against `naelonambul/sdlc-project-template-v2` too. Its classic protection is expected to show the documented "empty list" case.
   - Change no host settings.
5. **Local verification.**
   - Run `python3 scripts/repo.py verify --change host-setup-docs` and `verify --full`. No check may be `failed`, `blocked` or `not-run`. `docs/**` may route to no check, and `verify --full` covers the suite.
   - Run `status --change host-setup-docs`: `status: ok`, with no out-of-scope path.
6. **Candidate closure.** Add `closure.json` with:
   - `schema`: 1;
   - `baseline`: `{}`;
   - `packet_sha256`: computed by `repo.py`'s own closure logic;
   - `evidence`: citing only the step 5 local evidence.

   Confirm `stage=closed freshness=current readiness=ready closure=candidate`.
7. **Commit, push and PR.** Commit as the App, push with `agent-git`, and open a PR with `agent-gh`. The body starts with `Change-ID: host-setup-docs`.
8. **CI.** `summary` must pass on the head that contains the closure. Record the result in a PR comment. Any fix commit refreshes the closure evidence in the same commit.
9. **Human review and merge (owner).** The agent does not approve or merge.
10. **Post-merge.** The `push` run on `main` passes. `host-setup-docs` is `freshness=frozen closure=frozen` at the squash commit, and `lifecycle-docs` and `template-vnext-control-plane` remain frozen.

## Tests and proof

- **Docs-only.** Proof is:
  - the existing control-plane tests passing (`verify --full`);
  - step 4, which checks the documented JSON and commands against a live repository enforced by exactly that ruleset.
- **The recommended ruleset is the enforced one.** It is the same set of rules the `todo-cli-test` ruleset applied to both pilot merges.

## Risks and mitigations

- **Host API drift.** GitHub may change ruleset fields or its import UI. Mitigation: the read-only check exposes the difference, and the doc names the API endpoints, not UI details, as the reference.
- **Solo owner lockout.** One required approval with a single shared identity blocks every merge. Mitigation: recommend a separate agent identity, or another human reviewer. The zero-approval setting is documented only as a degraded mode that gives up the enforced human gate.
- **Over-trusting an App identity.** Mitigation: keep the trust-mode statement that `repo.py` still reports `unverified`, and forbid bypass actors.

## Rollback or recovery

- **Before merge:** close the PR.
- **After merge:** revert through a new `repository` change. The frozen packet is never edited.

## Open questions

None. v2's own host settings (classic protection and all merge methods enabled) differ from the recommendation. That is left for the owner to decide separately and does not block this docs change.
