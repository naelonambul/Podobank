# One-time host setup (GitHub)

GitHub does not copy repository settings, rulesets, or merge settings from a template. Configure each repository created from it separately. None of this changes the repository's contents.

## The setup, in two trust stages

The repository has two actors: the owner and a coding agent working under the repository's GitHub App, `mini26-agent`. The agent commits, pushes and opens every pull request. In the current trust stage, the owner approves and merges each pull request. The owner's decisions are recorded in the repository as `repo.py approve` claims on the change artifacts.

| | Now | Target |
|---|---|---|
| Who merges | The owner reviews and merges every pull request. The agent's merging is not yet trusted. | The agent merges once the `summary` check passes. |
| Owner's gates | `repo.py approve` claims, plus the review and merge on GitHub. | `repo.py approve` claims. |
| Ruleset | one required approval, last-push approval on | `required_approving_review_count: 0` |

The current stage is enforced by the ruleset, not by habit: with one required approval and `require_last_push_approval`, GitHub refuses the merge until the owner has approved the bot's last push. The switch to the target stage is one settings change, setting the required approval count to 0, after which the agent merges through the App's existing pull-request permission. Nothing in the repository changes.

The one rule this imposes on the agent: **the bot makes the last push.** A pull-request author cannot approve their own pull request, and the approver cannot be the last pusher. Because the bot authors and pushes last, the owner can approve. If a later bot change is needed, the bot pushes it before the owner reviews again.

Do not use the owner's `git push` or `gh pr` to substitute for the bot's authoring or last push. If the App wrappers are unavailable or reject an operation, stop and report the issue so the owner can restore the App path. The owner may use owner credentials for host setup, review, approval and merge, but not to author, push or create the agent's pull request.

## Merge policy

- Allow **squash merge** only, with one change per pull request. `repo.py` derives each change's closure anchor from the first-parent history of `main`, so merge commits also work if a project prefers them. Rebase merges do not, once a closure has been refreshed.
- Keep `main` linear enough that first-parent history is meaningful: no direct pushes that bypass pull requests.
- In the repository settings, allow squash merging only and disable merge commits and rebase merging.
- Optionally, enable automatic deletion of head branches.

## Protect `main` with a ruleset

Where the plan allows it (public repositories, or private repositories on GitHub Pro, Team, or Enterprise), one ruleset with **no bypass actors**:

| Rule | Setting | Why |
|---|---|---|
| Restrict deletions | on | |
| Block force pushes | on | first-parent history anchors closures |
| Require a pull request | 1 approval; dismiss stale approvals; require approval of the most recent push; squash only | the current trust stage; set approvals to 0 for the target stage |
| Require status checks | `summary`, source GitHub Actions; branches must be up to date | the validated candidate is the merge candidate |

The `summary` job of the `repository` workflow fails unless every other job succeeded.

Import-ready ruleset (`main-protection.json`):

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

To apply it, either go to **Settings → Rules → Rulesets → New ruleset → Import a ruleset**, or run `gh api -X POST repos/OWNER/REPO/rulesets --input main-protection.json`. `15368` is the GitHub Actions app.

Without a ruleset (for example a private repository on GitHub Free, where the rulesets API returns 403), nothing on the host enforces either stage: a red `summary` does not block the merge button, and anyone with write access can merge. Keep squash-only in the repository settings by hand, read the checks before merging, and treat the post-merge `push` run on `main`, which runs the full suite and validates closures, as the authoritative gate on the merged tree.

## The agent's identity

The sole bot account is GitHub App `mini26-agent`, displayed by GitHub as `mini26-agent[bot]`. `naelonambul-agent` is a retired display name for the same account, not a separate account. Every commit must use this identity:

```text
mini26-agent[bot] <332920101+mini26-agent[bot]@users.noreply.github.com>
```

Use the command wrappers from the repository directory. They dispatch by the first command word, so do not put `-C <path>` before a command.

| Wrapper | Use | Refused operations |
|---|---|---|
| `agent-git` | Local operations such as `add`, `commit`, `log` and `status`. It does not receive a token. | `push`, `pull`, `fetch`, `clone` and `ls-remote` |
| `agent-gh` | Remote `push`, `pull`, `fetch`, `clone` and `ls-remote` using the App token. `agent-gh pr ...` runs `gh pr ...`. | All other commands |

The agent cannot work on issues or use `gh api`. Do not call raw `git` or `gh` to bypass the wrappers. The App has pull-request merge permission, but permission is not authorization: in the current stage, the ruleset requires owner approval and repository policy reserves merge to the owner. The target stage in the table above remains a future host transition.

The GitHub App is owned by the repository owner, has no webhook, and is installed on selected repositories only, with these repository permissions and no others:

- Contents: read and write; Pull requests: read and write, including merge permission; Metadata, Checks and Actions: read.
- Not Administration, Workflows or Secrets. The App cannot change rulesets or settings. Its token has no `workflows` permission, so a push touching `.github/workflows/**` is rejected; stop and tell the owner, who handles workflow changes. The App cannot approve a pull request as the owner.

Add each new repository to the App's installation before an agent starts work: **Settings → Applications → Installed GitHub Apps → the App → Configure → Repository access → Only select repositories → Select repositories → Save**. Only the owner can do this, and creating a repository from the template does not do it. Until then, minting a token for that repository fails, for example with HTTP 422, and the agent cannot push under its identity. If the token helper has its own repository allowlist, add the repository there too. Mint one token to confirm before starting.

Keep the App's private key outside every repository, readable only by the owner, never in agent context. Mint short-lived installation tokens restricted to one repository; they expire after an hour and are never stored. Never add the App as a ruleset bypass actor. The token helper is host-specific and lives outside the repository.

## Read-only host check

These commands only read and are for the owner to run when checking host settings. The agent cannot use `gh api`; this owner-only access does not replace the bot's authoring, push or pull-request path.

```sh
gh api repos/OWNER/REPO/rules/branches/main --jq '[.[].type] | sort'
# with the ruleset: ["deletion","non_fast_forward","pull_request","required_status_checks"]
gh api repos/OWNER/REPO/rulesets --jq '.[] | {id, name, enforcement}'
gh api repos/OWNER/REPO/rulesets/ID --jq '{bypass_actors, rules}'
gh api repos/OWNER/REPO --jq '{allow_squash_merge, allow_merge_commit, allow_rebase_merge}'
```

Expect the ruleset's `enforcement` to be `active` with empty `bypass_actors`, `summary` among its required status checks, the approval count that matches the current stage, and the repository merge settings to allow squash only. Classic branch protection shows up in `rules/branches/main` as an empty list; check it in the UI instead.

## What approval means here

`repo.py approve` writes a digest-bound claim that the owner reviewed exactly those bytes. `repo.py status` reports it as `unverified`: it detects a stale or edited artifact, and it does not prove who ran the command. The template has no provider path that could prove more, and does not pretend otherwise. In the current stage the GitHub approval and merge by the owner add a second, host-side record; in the target stage the claims are the owner's record.
