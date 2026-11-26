# Development workflow

Work in this repository runs as two nested loops. The backlog loop decides
what to do next. The PR loop turns one unit of that work into one merged pull
request.

```text
Backlog loop   one iteration = one batch of Linear issues
  PR loop      one iteration = one merged pull request
```

Scope only moves outward: a PR that uncovers a new line of work files a Linear
issue. Defects move inward: anything found while a PR is open is fixed in that
PR, never filed for later.

## Roles

- **The operator** (Jim) owns direction and rules on genuine design forks. A
  question goes to the operator only at such a fork, always with a
  recommendation first; with no answer in two minutes, proceed with the
  recommendation and say so.
- **Claude** runs everything else: the backlog, the code, the tests, the
  local review, the PR, the merge and the close-out. Claude may write code
  directly or hand a bounded task to a sub-agent (`Agent`). A sub-agent task
  carries a time box and "first commit within 30 minutes", never creates
  branches, never pushes, and never touches review threads.
- **Review is done by agents**: the local review agents, and Devin Review on
  the PR. There is no human review gate.

## The tools

- **Linear** is the single funnel. Issues for this repo live in the
  **Punt Labs** team as `PL-*` and name `oo-ratchet` or `python-oo-ratchet`
  in the title or description.
- **beadle** (the `email` MCP server) sends the recap emails to
  `jim@punt-labs.com`. See `.punt-labs/beadle/CLAUDE.md`.
- **vox** (the `mic` MCP server) speaks to the operator. Use it for the two
  moments the operator should hear without watching the terminal: a ruling is
  needed, and a PR merged. One sentence each, also written in the
  conversation. See `.punt-labs/vox/CLAUDE.md`.
- **lux** (the `lux` MCP server) shows tables in a window the operator can
  see. Use `scene_table` for the batch at selection (issue, title, priority,
  status) and for gate results when a ratchet run reports more than a few
  files (file, metric, base, current, verdict). Keep the same `scene_id` per
  purpose so a refresh replaces the old table.

## Backlog loop

```text
function backlog_loop():
    # 1. INTAKE — every signal becomes a Linear issue or is closed with a reason
    for signal in [github_issues, dependabot_alerts, biff_messages,
                   operator_requests, new_scope_found_while_working]:
        if duplicate(signal):  link to the existing issue and close it
        elif invalid(signal):  close it with the reason
        else:                  create a Linear issue linking the source

    # 2. VALIDATE — an issue must still be true before it is worked
    for issue in the candidates for this batch:
        reproduce it, or re-check its premise, against current main
        confirm nothing merged since has superseded it
        confirm it reverts as one unit (split or merge it if not)

    # 3. ORDER — automatic; ask only at a genuine fork
    sort by: security severity
           > a gate that passes something it should fail, or fails an
             adopter repo (vox, quarry, lux, z-spec) wrongly
           > the epic already in progress
           > debt that makes the next changes cheaper
           > features

    # 4. EXECUTE
    show the batch with lux scene_table
    for unit in the batch: pr_loop(unit)

    # 5. CLOSE OUT
    send the batch recap with beadle: intake dispositions, issues closed at
        validation, order changes, PRs merged
```

A gate that wrongly passes is the worst defect this repository can ship: every
adopter trusts it. It outranks every feature.

## PR loop

```text
function pr_loop(unit):
    # A. BUILD
    branch from main (in a worktree)
    first commit: the smallest change a user would notice, with its test;
        a bug fix starts with a test that fails on the unfixed code, and the
        failing and passing output go in the commit message or the PR
    further commits, each passing make lint type test
    make check, with the merge-base flags (see CLAUDE.md), before the PR
    make update-oo / update-coupling as the change requires; commit the
        baseline and audit files with the source

    # B. LOCAL REVIEW — until a round leaves nothing to fix
    local_review(full diff)

    # C. DEMO — the real entry point, before the PR opens
    demo(unit)

    # D. SHIP
    push; open the PR; the description says what changed, how it was proven,
        and pastes the demo command and output
    start /loop 3m polling the PR (never gh pr checks --watch)

    # E. EACH POLL
    if CI failed: fix it, local_review(fix diff), push
    for each review thread or finding: fix it now or answer it with the
        exact finding, the reason, and file:line; resolve the thread
    when no review is pending and no finding is open: switch to /loop 15m
    if merge_gate(): squash-merge with --delete-branch; close_out()

function local_review(diff):
    for round in 1..5:
        if first full diff or diff >= 20 lines:
            run code-reviewer, silent-failure-hunter, and `qodo review`
        else:
            run `qodo review`
        after round 1, scope each review to regressions and Highs inside
            this diff only
        if round == 5 and a finding needs a fix: ask the operator; stop
        fix every finding, or dismiss it with the reason and file:line
        if nothing was fixed: return clean
        commit; diff = this round's fix diff

function demo(unit):
    write down the expected output first
    run the changed gate through the oo-ratchet CLI:
        - on this repo: uv run oo-ratchet <gate> src/oo_ratchet/ ...
        - for a change an adopter would see, from the adopter's root:
          uvx --from <this checkout> oo-ratchet <gate> <its src> --check
    include one input the gate must refuse (a regression, a bad flag, a
        missing base) and confirm it fails with a clear message
    paste the commands and output into the PR as "demo confirmed: <sha>"
    a demo that does not match expectation is a finding, fixed in this PR

function merge_gate() -> bool:
    return CI green on the PR head
       and Devin Review has reported, or 30 minutes passed since the PR opened
       and every finding is fixed on the head or answered with a reason
       and zero unresolved review threads
       and a "demo confirmed" comment names the head, or every commit after
           it touches only docs/, tests/, *.md or ratchet state files
    # When true: merge now, explicitly. Never --auto, never --admin.

function close_out():
    stop the poll loop
    set the Linear issue(s) Done
    delete the branch; update main
    speak one sentence with vox: what merged
    send the merge recap with beadle to jim@punt-labs.com: what changed,
        why, how it was proven (test names, demo output), review findings and
        their answers, ratchet deltas, follow-up issues filed
    start the next unit
```

### PR size

Size a PR for throughput: several small issues together, or one coherent slice
of a large one. The one structural rule is that a PR reverts as a unit. A docs
fix, a ratchet paydown or an adjacent bug fix riding along is welcome.

### Releases

A release is its own PR on a `release/vX.Y.Z` branch: bump `version` in
`pyproject.toml`, move the `CHANGELOG.md` entries under the new version, merge,
then push the `vX.Y.Z` tag. CI lets `release/*` and `post-release/*` branches
pass the OO gate without a metric improvement. The release recap names the
adopter repos that pin `punt-oo-ratchet` and the version each pins.

## Invariants

1. Linear is the single funnel; every piece of work is an issue first.
2. A satisfied merge gate means merge now.
3. A finding is fixed in this PR or answered with a reason when it arrives;
   never deferred to an issue.
4. A push restarts CI, not review.
5. Close-out (Linear, branch, vox, recap) is part of the loop.
6. No migration, compatibility shim or version-bridge code. When a change
   supersedes old behavior, the old path is deleted in the same change. The
   one exception is the baseline and audit file formats, which adopter repos
   read: change them only with a release note naming each adopter.
