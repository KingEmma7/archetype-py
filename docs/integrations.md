# CI and Integrations

[← Back to README](../README.md)

Running Archetype in CI, in Git hooks, and in pytest.

## GitHub Actions

The simplest way to run Archetype in GitHub Actions is the composite
action published from this repository — one line instead of a full job
definition, checkout and Python setup included.

```yaml
name: Architecture

on:
  pull_request:
  push:
    branches: [main]

jobs:
  archetype:
    runs-on: ubuntu-latest
    steps:
      - uses: MossabArektout/archetype-py@v0.6.0
```

Inputs (all optional):

| Input | Default | Purpose |
|---|---|---|
| `path` | `.` | Path to the project to check. |
| `python-version` | `3.11` | Python version to run Archetype with. |
| `version` | latest | Pin a specific `archetype-py` version. |
| `args` | *(none)* | Extra arguments appended to `archetype check`, e.g. `--format json`. |
| `github-annotations` | `true` | Emit inline PR annotations when supported. |
| `checkout` | `true` | Set to `false` if your job already has its own `actions/checkout` step. |
| `fetch-depth` | `0` | Git history depth; keep full history if you use `--changed-from` or `@since`. |

```yaml
- uses: MossabArektout/archetype-py@v0.6.0
  with:
    path: backend/
    args: --format json
```

The action is versioned with the package: every release tag from `v0.6.0`
onward can be used as the ref, so bump it the same way you would any other
dependency. Its definition lives in [`action.yml`](../action.yml) at the root
of this repository, so `main` is always the newest unreleased behavior and
tagged releases are what's safe to depend on in CI. By default the action
installs the latest `archetype-py` from PyPI; set `version` to pin it too.

<details>
<summary>Or, define the job by hand (equivalent, more control)</summary>

```yaml
name: Architecture

on:
  pull_request:
  push:
    branches: [main]

jobs:
  archetype:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python -m pip install archetype-py
      - run: archetype check .
```

Inline PR annotations:

```yaml
- run: archetype check . --github-annotations
```

</details>

## GitLab CI

The command is the same as anywhere else — install Archetype, then run
`archetype check .`. Only the surrounding job syntax differs:

```yaml
archetype:
  image: python:3.11
  stage: test
  script:
    - python -m pip install archetype-py
    - archetype check .
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    - if: '$CI_COMMIT_BRANCH == "main"'
```

## Azure Pipelines

```yaml
trigger:
  branches:
    include:
      - main

pr:
  branches:
    include:
      - main

pool:
  vmImage: ubuntu-latest

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: "3.11"
  - script: |
      python -m pip install archetype-py
      archetype check .
    displayName: "Run Archetype"
```

## Pre-commit Hook

Archetype can catch violations before a commit is created, not after it reaches CI. There are two ways to wire this up: the [pre-commit framework](https://pre-commit.com/) (recommended if your project already uses it), or Archetype's own built-in hook installer.

### Using the pre-commit framework

Archetype ships a [`.pre-commit-hooks.yaml`](../.pre-commit-hooks.yaml) manifest, so it can be added to `.pre-commit-config.yaml` like any other tool:

```yaml
repos:
  - repo: https://github.com/MossabArektout/archetype-py
    rev: v0.6.0 # use the latest tag
    hooks:
      - id: archetype
```

Then install the hook and run it:

```bash
pre-commit install
pre-commit run archetype --all-files
```

The hook runs `archetype check` against the repository root on every commit (it does not accept a `--changed-from`-style per-file mode, since rules need the full import graph). `pre-commit` installs Archetype into its own managed environment, so your project's virtualenv does not need Archetype installed for the hook to work.

### Using the built-in installer

If you don't use the pre-commit framework, Archetype can install a managed Git hook directly:

```bash
archetype install-hook .
```

```
Installed pre-commit hook at /path/to/project/.git/hooks/pre-commit
Hook command: archetype check /path/to/project
```

The hook is written to the repository's `pre-commit` hook path and made executable. The installed block runs `archetype check` against the repository root, so every commit is checked against the full project, not only the staged files.

### Verifying the hook

Make a commit. A clean project reports its summary and the commit proceeds:

```
$ git commit -m "add service layer"
Summary: 1 passed, 0 failed, 0 warned, 0 skipped, 1 total rules.
[main 1a2b3c4] add service layer
```

A commit that breaks a rule prints the violation and is rejected:

```
$ git commit -m "add cycle"
Cycles
======
  ✗ no-cycles
    - myapp/a.py:1
        imports myapp.b
  0 passed, 1 failed
Summary: 0 passed, 1 failed, 0 warned, 0 skipped, 1 total rules.
```

The commit is not created. Use `git commit --no-verify` to bypass the hook deliberately.

### Requirements and behaviour

`archetype` must be available on `PATH` for the hook to run. The hook checks this first and fails the commit with a clear message rather than passing silently:

```
archetype: CLI not found on PATH. Install archetype to run checks.
```

If you install Archetype into a virtualenv, that environment must be active when you commit, or Git tools that run outside it will not find the CLI.

The command is safe to re-run and reports what it did:

| Situation | Result |
| --- | --- |
| No hook present | `Installed pre-commit hook at ...` |
| Archetype block already current | `Archetype pre-commit hook already installed at ...` |
| Archetype block present but outdated | `Updated Archetype block in pre-commit hook at ...` |
| Some other hook already present | `Appended Archetype block to existing pre-commit hook at ...` |

Archetype only owns the region between its markers, so an existing hook is preserved:

```sh
# >>> archetype pre-commit hook >>>
...
# <<< archetype pre-commit hook <<<
```

Because the block is appended, an existing hook that exits before reaching it will prevent the Archetype check from running. If your hook ends with an explicit `exit`, move the Archetype block above it.

To uninstall, delete that block from `.git/hooks/pre-commit` (or delete the file if Archetype is its only content). Running the command outside a Git repository exits with status `1`:

```
Error: Unable to resolve git hooks path: fatal: not a git repository (or any of the parent directories): .git
```

## Pytest

Archetype ships a pytest plugin. With the package installed, pytest can collect rules from `architecture.py` and report them as test items.

```bash
pytest
```

This is useful when architecture rules should live beside the rest of the test suite.

## CODEOWNERS Integration

A generic "CI failed" tells whoever opened the PR that something broke, not
who is actually responsible for the module involved. If a
[`CODEOWNERS`](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
file exists, Archetype reads it automatically — no separate ownership file
to maintain — and routes each violation to the team or user who owns the
affected path:

```text
General
=======
  ✗ api-must-not-import-db
    - myapp/api/users.py:7
        imports myapp.db.internal.session
        owner: @acme/data-team
```

The owner also appears in JSON (`owners`), SARIF (`properties.owners`), and
GitHub Actions inline annotations (prefixed to the message, e.g.
`@acme/data-team: api-must-not-import-db: ...`).

Archetype checks the same locations and precedence GitHub itself uses:

1. `.github/CODEOWNERS`
2. `CODEOWNERS` (repository root)
3. `docs/CODEOWNERS`

Matching follows CODEOWNERS' own last-match-wins rule, same as
`.gitignore`: later patterns in the file override earlier ones for the
same path. No configuration is required — if none of the three files
exist, violations are reported exactly as before.

## Shell Completion

Archetype can generate tab-completion scripts for bash, zsh, and fish using [Click's built-in completion support](https://click.palletsprojects.com/en/stable/shell-completion/).

Add the appropriate line to your shell's startup file:

```bash
# Bash: add to ~/.bashrc
eval "$(archetype completion bash)"

# Zsh: add to ~/.zshrc
eval "$(archetype completion zsh)"

# Fish: add to ~/.config/fish/config.fish
archetype completion fish | source
```

Restart your shell (or `source` the file) and completions are available for commands, options, and flags:

```bash
$ archetype ch<TAB>
check

$ archetype check --for<TAB>
--format
```

Run `archetype completion` with no argument to auto-detect your shell from `$SHELL`, or pass it explicitly (`archetype completion zsh`). Completion is regenerated by Click at your shell's own startup, so it always reflects the installed Archetype version — no separate update step is needed after upgrading.
