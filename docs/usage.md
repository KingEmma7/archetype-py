# Using the CLI

[← Back to README](../README.md)

Every command, flag, and configuration option, plus the features for adopting Archetype in an existing codebase.

## Commands

| Command | Purpose |
|---|---|
| `archetype init [path]` | Generate a starter `architecture.py`. |
| `archetype init [path] --infer` | Generate rules that already pass from the current import graph. See [Inferring Rules From Your Code](rules.md#inferring-rules-from-your-code). |
| `archetype init [path] --dry-run` | Print the generated `architecture.py` instead of writing it. |
| `archetype check [path]` | Load `architecture.py` and run all registered rules. |
| `archetype check [path] --group <name>` | Run only rules in one group. |
| `archetype check [path] --format json` | Emit machine-readable JSON report output. |
| `archetype check [path] --format sarif` | Emit SARIF 2.1.0 output for code scanning integrations. |
| `archetype check [path] --quiet` | Show only failures and warnings. |
| `archetype check [path] --no-cache` | Force a fresh import graph rebuild. |
| `archetype check [path] --exclude <pattern>` | Exclude paths from analysis and reporting. |
| `archetype check [path] --changed-from <ref>` | Report only violations in Python files changed from a Git ref. |
| `archetype check [path] --write-baseline <file>` | Write the current violations to a baseline file. |
| `archetype check [path] --baseline <file>` | Suppress matching baseline violations. |
| `archetype check [path] --github-annotations` | Emit GitHub Actions inline annotation commands. |
| `archetype check [path] --record-trend <file>` | Append this run's violation counts to a trend history file. See [Trend Reporting](#trend-reporting). |
| `archetype doctor [path]` | Explain detected project layout, graph, config, cache, and rule context. |
| `archetype graph [path] --format mermaid\|json` | Export the discovered import graph. |
| `archetype trend <file> --format text\|json` | Show violation counts recorded over time. See [Trend Reporting](#trend-reporting). |
| `archetype install-hook [path]` | Install or update a managed Git pre-commit hook. See [Pre-commit Hook](integrations.md#pre-commit-hook). |
| `archetype completion [bash\|zsh\|fish]` | Print a shell completion script (auto-detects your shell if omitted). See [Shell Completion](integrations.md#shell-completion). |

Common check flag examples:

```bash
# Run only rules in one group
archetype check . --group "Layer boundaries"

# Emit machine-readable JSON
archetype check . --format json

# Emit SARIF for code scanning integrations
archetype check . --format sarif > archetype.sarif

# Show only failures and warnings
archetype check . --quiet

# Ignore the import graph cache and rebuild from source
archetype check . --no-cache
```

## Example Output

What Archetype prints for the three outcomes you will actually see.

### A passing run

Every rule holds. Each group reports its own tally, and the run exits `0`:

```text
Boundaries
==========
  ✓ api-must-not-import-db
  ✓ services-must-not-import-api
  2 passed, 0 failed

Cycles
======
  ✓ no-import-cycles
  1 passed, 0 failed

Internals
=========
  ✓ internal-helpers-stay-private
  1 passed, 0 failed
Summary: 4 passed, 0 failed, 0 warned, 0 skipped, 4 total rules.
```

### A failing run

Each violation names the file and line of the offending import, and the
module it resolved to. The run exits `1`:

```text
Boundaries
==========
  ✗ api-must-not-import-db
    - myapp/api/routes.py:2
        imports myapp.db.session
  ✓ services-must-not-import-api
  1 passed, 1 failed

Cycles
======
  ✓ no-import-cycles
  1 passed, 0 failed

Internals
=========
  ✗ internal-helpers-stay-private
    - myapp/services/reports.py:1
        imports myapp.core.internal.helpers
  0 passed, 1 failed
Summary: 2 passed, 2 failed, 0 warned, 0 skipped, 4 total rules.
```

`myapp/api/routes.py:2` is the exact import to remove, so the output can be
pasted into an editor or clicked in a terminal that linkifies paths.

### A warning run

A rule whose pattern matches no modules is reported as a warning rather than
a silent pass, with suggestions from the modules Archetype did find. This is
usually a typo or a pattern left behind after a rename:

```text
Boundaries
==========
  ⚠ controllers-must-not-import-db
    Source pattern 'myapp.controllers' matched 0 modules. Did you mean: myapp.core, myapp.core.internal.helpers, myapp.core.internal?
  0 passed, 0 failed
Summary: 0 passed, 0 failed, 1 warned, 0 skipped, 1 total rules.
```

Warnings do not fail the run — this example exits `0`. See
[Diagnostics](#diagnostics) for the patterns that are checked, and
[Exit Codes](#exit-codes) for the full list.

## Supported Layouts

Archetype detects common Python project layouts:

- flat packages, such as `myapp/`
- single `src/` layouts, such as `src/myapp/`
- namespace packages without `__init__.py`
- monorepos with multiple nested `*/src` roots

Use `archetype doctor .` to inspect what Archetype detected.

## Diagnostics

Use `doctor` when a rule does not behave as expected:

```bash
archetype doctor .
```

It reports detected layout, package roots, Python module count, import edge count, config source, excludes, cache status, detected layers, internal packages, and whether `architecture.py` exists.

Export the import graph for debugging or documentation:

```bash
archetype graph . --format mermaid
archetype graph . --format json
```

When a source, target, allowed, layer, boundary, cycle, or naming pattern matches no modules, Archetype reports a diagnostic warning with likely suggestions. This helps catch typos and stale rules instead of silently passing them.

## Configuration

Archetype auto-discovers `archetype.toml` from the project root passed to `archetype check [path]`.

```toml
format = "json"
quiet = true
group = "Layer boundaries"
exclude = ["/vendor/", "/migrations/"]
workers = 4
cache = true

[rules]
"legacy-boundary" = "warning"

[rules."deprecated-layer-rule"]
policy = "off"
```

Supported defaults:

- `format`: `"text"`, `"json"`, or `"sarif"`
- `quiet`: `true` or `false`
- `group`: rule group name
- `exclude`: string or list of strings
- `workers`: integer greater than or equal to `1`
- `cache`: `true` or `false`

Per-rule policy:

- `error`: fail the run when the rule fails (default)
- `warning`: report violations without failing the run or pytest
- `off`: skip the rule without executing it

Rule names are matched exactly against the name passed to `@rule("...")`.

Precedence:

1. CLI flags
2. `archetype.toml`
3. built-in defaults

For compatibility, if `archetype.toml` is missing, Archetype still reads legacy `[tool.archetype]` settings from `pyproject.toml`.

## Path Exclusions

Exclude generated code, vendored dependencies, migrations, or other noisy paths:

```bash
archetype check . --exclude /vendor/ --exclude /migrations/
```

Or define the defaults in `archetype.toml`:

```toml
exclude = ["/vendor/", "/migrations/"]
```

## Baseline Mode

Baseline mode lets you adopt Archetype in an existing codebase without failing CI on every old violation.

Create a baseline:

```bash
archetype check . --write-baseline archetype-baseline.json
```

Run against that baseline:

```bash
archetype check . --baseline archetype-baseline.json
```

Matching old violations are suppressed. New blocking violations still fail with exit code `1`.

## Changed-Files Mode

Use diff scope for large projects or pull request checks:

```bash
archetype check . --changed-from origin/main
```

`<ref>` can be a branch name or commit SHA. Text output shows a scope banner, and JSON output includes a `scope` object with the changed file metadata.

## Trend Reporting

`archetype check --format json` already reports a violation count for that
one run. Trend reporting stores that same count over time so you can show
the story, not just today's pass/fail: "340 violations in January, 210 in
June, 90 today." No new analysis happens — the count that's already
computed is just appended to a small history file instead of discarded.

Record one entry per run, in CI or locally:

```bash
archetype check . --record-trend archetype-trend.jsonl
```

Each run appends one JSON line — safe to run repeatedly, nothing is
overwritten. Pairs naturally with [baseline mode](#baseline-mode) for
tracking a legacy-debt paydown over time.

View the recorded history:

```bash
archetype trend archetype-trend.jsonl
```

```text
Recorded at             Violations  Passed  Failed  Warned
----------------------------------------------------------
2026-01-01T00:00:00Z           340       0       1       0
2026-04-01T00:00:00Z           260       0       1       0
2026-06-01T00:00:00Z           210       0       1       0
2026-08-29T00:00:00Z            90       1       0       0

Trend (4 runs): █▆▄▁
340 -> 90 violations (down 73.5%)
```

Or get the raw series for your own dashboard/spreadsheet:

```bash
archetype trend archetype-trend.jsonl --format json
```

The trend file is a plain [JSON Lines](https://jsonlines.org/) file — one
independent JSON object per line — so a CI job can append to it without
ever reading the existing history first. Concurrent writes from parallel
CI jobs aren't guaranteed to interleave safely; record trend data from a
single job per run if that matters for your setup.

## Exit Codes

- `0`: no blocking failures
- `1`: one or more blocking failures

Warning-only rules do not fail the process. When `--baseline` is used, exit code `1` means there are new blocking violations not present in the baseline.

## Troubleshooting

`Error: architecture.py not found`

Run `archetype init .` in your project root, or pass the correct path to `archetype check <path>`.

Rules seem to do nothing

Confirm the functions are decorated with `@rule("...")`. Undecorated functions are not registered.

Pattern matches no modules

Run `archetype doctor .`, then check that your patterns use fully qualified module names such as `myapp.api`, not file paths such as `src/api.py`.

`@since(...)` behaves unexpectedly

Use `YYYY-MM-DD` format and make sure Git history is available in the checked path.

Imports are missing from the graph

Check that modules live under detected package roots. `archetype doctor .` shows the roots Archetype is using.
