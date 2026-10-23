# Writing Rules

[← Back to README](../README.md)

Rules live in `architecture.py` at your project root. A rule is a plain Python function registered with `@rule("name")`; inside it, you call one or more checks. A rule passes when its checks find nothing, and fails with every violation they found.

```python
from archetype import imports, rule

@rule("api-must-not-import-db")
def api_must_not_import_db() -> None:
    imports("myapp.api").must_not_import("myapp.db")
```

## Module Patterns

Every check selects modules with a dotted pattern:

| Pattern | Matches |
|---|---|
| `myapp.api` | `myapp.api` and everything beneath it (`myapp.api.routes`, `myapp.api.v1.users`, ...) |
| `myapp.*` | Each direct child of `myapp`, without its submodules (`*` matches within one segment) |
| `myapp.**.models` | A `models` module at any depth under `myapp` (`**` matches any number of segments) |
| `**` | Every module in the project |

Patterns use module names, not file paths: `myapp.api`, not `src/myapp/api.py`. Only imports between your own modules are checked. The standard library and third-party packages are not part of the graph, so you never need to allow `os` or `requests`.

## All Checks

| Check | Fails when |
|---|---|
| `imports(src).must_not_import(target)` | A module in `src` directly imports a module in `target`. |
| `imports(src).must_not_depend_on(target)` | A module in `src` reaches `target` through any chain of imports. The JSON message shows the full path, e.g. `myapp.api.users → myapp.services.auth → myapp.db.session`. |
| `imports(src).must_only_import_from(*allowed)` | A module in `src` imports anything outside the `allowed` patterns. |
| `imports(src).has_no_cycles()` / `no_cycles(pattern)` | The selected modules import each other in a loop. |
| `imports(src).max_depth(n)` | An import reaches more than `n` dotted segments deep. See [depth and coupling](#import-depth-and-coupling-limits). |
| `imports(src).fan_in_at_most(n)` / `fan_out_at_most(n)` | A module is imported by, or imports, more than `n` modules. |
| `layers([...]).are_ordered()` | A lower layer imports a higher one. See [strict layering](#strict-layering-no-skipping). |
| `layers([...]).are_adjacent()` | Any cross-layer import other than to the layer directly below. |
| `independent([...])` | Two of the listed packages import each other. See [independent packages](#independent-packages). |
| `module(protected).only_imported_within(parent)` | `protected` is imported from outside `parent`. |
| `public_api(package).enforce()` | An import reaches past the package's `__all__` into its internals. See [public API enforcement](#public-api-enforcement). |
| `deprecated(pattern, sunset=..., reason=...)` | The module is imported from anywhere outside itself. See [deprecating a module](#deprecating-a-module). |
| `classes_in(pattern).all_match(regex)` | A class in the matched modules has a name that doesn't fully match `regex`. |
| `functions_in(pattern).must_include(name)` | A matched module doesn't define a top-level function called `name`. |

`imports` is importable from `archetype`; everything else comes from `archetype.rules`.

A few of these in practice:

```python
from archetype import imports, rule
from archetype.rules import classes_in, functions_in, module

@rule("domain-stays-pure")
def domain_stays_pure() -> None:
    # The domain layer may only use itself and shared core code.
    imports("myapp.domain").must_only_import_from("myapp.domain", "myapp.core")

@rule("api-never-reaches-db")
def api_never_reaches_db() -> None:
    # Not even indirectly, through a service that leaks a session.
    imports("myapp.api").must_not_depend_on("myapp.db")

@rule("core-internals-are-private")
def core_internals_are_private() -> None:
    module("myapp.core.internal").only_imported_within("myapp.core")

@rule("services-are-named-services")
def services_are_named_services() -> None:
    classes_in("myapp.services").all_match(r"[A-Z]\w*Service")

@rule("migrations-define-upgrade")
def migrations_define_upgrade() -> None:
    functions_in("myapp.migrations.*").must_include("upgrade")
```

If a pattern matches no modules, the rule is reported as a warning with suggestions instead of silently passing. See [diagnostics](usage.md#diagnostics).

## Rule Helpers

Rules are plain Python functions registered with decorators.

| Helper | Purpose | Example |
|---|---|---|
| `@rule("name")` | Register a rule with a display name. | `@rule("api-not-db")` |
| `@warn` | Report violations without failing the exit code. | `@warn` |
| `@skip` / `@skip(reason="...")` | Temporarily skip a rule. | `@skip(reason="Refactor in progress")` |
| `@since("YYYY-MM-DD")` | Only report violations in files modified after a date. | `@since("2026-01-01")` |
| `@escalate(warn_until="YYYY-MM-DD")` | Warning-only through the date, then a hard failure automatically. | `@escalate(warn_until="2027-06-30")` |
| `group("name")` | Assign enclosed rules to a group. | `with group("Layer boundaries"):` |

Decorator order tip: write `@rule(...)` as the top decorator, above wrappers such as `@warn`, `@skip`, `@since`, or `@escalate`.

```python
@rule("warning-example")
@warn
def warning_example() -> None:
    ...
```

## Inferring Rules From Your Code

`archetype init --infer` reads your import graph and writes an `architecture.py` describing the architecture you already have:

```text
$ archetype init . --infer

Analyzed shop: 25 modules, 22 internal imports, 8 top-level components.

  Layers        api → services → repositories → db → core
  Independent   billing, orders, shipping
  Protected     core.internal (already leaking)
  Cycles        found in 2 places (added as a warning)
  Likely leaks  db → api (1×)

Wrote ./architecture.py: 5 rules, no failures today, 3 warnings pointing at problems that already exist.
Run archetype check . to see them.
```

It looks at the top-level packages inside your project (`shop.api`, `shop.billing`, ...) and how they import each other, then proposes:

| Rule | Inferred from |
|---|---|
| `layers([...]).are_ordered()` | The longest chain of packages where each imports the next and nothing imports back up. |
| `independent([...])` | Packages that use other packages but never reach each other, directly or indirectly. Typically feature packages like `billing` / `orders` / `shipping`. |
| `module(...).only_imported_within(...)` | `internal` and `_private` subpackages that are only imported from inside their parent. |
| `no_cycles(...)` | Always added. It becomes a `@warn` rule when import cycles already exist. |
| `imports(...).must_not_import(...)` (`@warn`) | Likely leaks: a rare import that runs against the rest of the code and closes a loop, like a single `db → api` import next to many `api → … → db` imports. |

Every generated rule runs through the rule engine before the file is written. Rules that hold today are enforced. Rules that describe a problem that already exists are marked `@warn`, so they are reported but never fail the run. Fix the problem, then delete the `@warn` line. When a likely leak breaks the full layering, you get two layer rules: an enforced one that leaves out the layer the leak reaches into, and a `@warn` one for the full stack.

The generated file is commented with the evidence for each rule (import counts, file and line of each leak, example cycles), so you can review it before committing:

```python
with group("Independence"):
    # These packages never import each other today, directly or indirectly.
    # Keep them decoupled: share code through a lower layer instead.
    @rule("independent-packages")
    def independent_packages() -> None:
        independent(
            [
                "shop.billing",
                "shop.orders",
                "shop.shipping",
            ]
        )
```

Useful to know:

- `--dry-run` prints the generated file instead of writing it.
- Tests, docs, examples, benchmarks and scripts are left out of inference. Exclusions from `archetype.toml` apply too.
- Modules that import the root package itself (`import myapp`) hide what they actually use. Those packages are left out of independence rules, and the summary tells you how many there are.
- Packages that import each other heavily in both directions cannot be layered. They are listed as *tangled* rather than guessed at.

## Public API Enforcement

`module(...).only_imported_within(...)` protects a module by name. `public_api(...)` protects it by declared interface: a package states what it exposes with `__all__`, and any import that reaches past that — straight into an internal submodule — is a violation, regardless of which module is doing the reaching.

```python
# billing/__init__.py
from .invoice import Invoice

__all__ = ["Invoice"]
```

```python
from archetype import rule
from archetype.rules import public_api

@rule("billing-public-interface")
def billing_public_interface() -> None:
    public_api("billing").enforce()
```

```python
from billing import Invoice          # OK: goes through the declared interface
from billing.invoice import Invoice  # Violation: reaches past it into billing.invoice
```

A submodule can be declared public in its own right by naming it in `__all__` (`__all__ = ["Invoice", "reporting"]` allows `import billing.reporting` and everything beneath it). `public_api(...)` requires the target package to declare `__all__` as a literal list or tuple of strings in its `__init__.py`; it raises a clear error naming the file if `__all__` is missing, computed, or the package has no `__init__.py` (namespace packages are not supported, since there is nowhere to declare an interface). A pattern can also match several packages at once, e.g. `public_api("myapp.*")` to enforce every top-level package's interface in one rule.

## Strict Layering: No Skipping

`layers([...]).are_ordered()` stops a lower layer from importing an upper one, but still allows a top layer to reach straight past a middle layer into the bottom one. `are_adjacent()` closes that gap: every cross-layer import must go through the layer directly below it.

```python
from archetype.rules import layers

@rule("layers-are-strict")
def layers_are_strict() -> None:
    layers(["myapp.api", "myapp.services", "myapp.db"]).are_adjacent()
```

```python
# myapp/api.py
from myapp import services  # OK: the adjacent layer
from myapp import db        # Violation: skips over services
```

`are_adjacent()` is a strict superset of `are_ordered()` — it also catches upward imports — so call one or the other for a given layer list, not both, to avoid the same edge being reported twice.

## Independent Packages

Layers describe *vertical* structure. `independent([...])` describes *horizontal* structure: sibling packages that must not import each other, and share code only through a lower layer.

```python
from archetype.rules import independent

@rule("features-are-independent")
def features_are_independent() -> None:
    independent(["myapp.billing", "myapp.orders", "myapp.shipping"])
```

```python
# myapp/orders/cart.py
from myapp.core import money       # OK: a shared lower layer
from myapp.billing import invoices  # Violation: orders imports billing
```

Imports within a single package are allowed. Every cross-package import is reported, not just the first one.

## Import Depth and Coupling Limits

Three checks on `imports(...)` catch structural drift that shows up gradually, rather than one specific forbidden import:

| Check | Flags | Example |
|---|---|---|
| `max_depth(n)` | Any import reaching more than `n` dotted segments deep | `imports("**").max_depth(3)` |
| `fan_in_at_most(n)` | A matched module imported by more than `n` other modules | `imports("myapp.core.*").fan_in_at_most(15)` |
| `fan_out_at_most(n)` | A matched module importing more than `n` other modules | `imports("myapp.*").fan_out_at_most(10)` |

```python
from archetype import imports

@rule("no-deep-reaches")
def no_deep_reaches() -> None:
    imports("myapp").max_depth(4)

@rule("core-utils-not-overloaded")
def core_utils_not_overloaded() -> None:
    # A low-level utility with too many importers is a hidden hub; catch
    # it before "just add one more caller" becomes a refactor no one can do.
    imports("myapp.core.utils").fan_in_at_most(20)

@rule("handlers-not-doing-too-much")
def handlers_not_doing_too_much() -> None:
    # A module that imports too much is usually a module doing too much.
    imports("myapp.api.*").fan_out_at_most(8)
```

Fan-in and fan-out violations point at the module's own defining file, since the violation is about its overall shape rather than one specific import line.

## Deprecating a Module

`deprecated(pattern, sunset=..., reason=...)` flags every import of a module or package from outside itself, with a message that names the reason and counts down to (or past) the sunset date — self-imports within the deprecated subtree, such as its own `__init__.py` re-exporting a sibling submodule, are not flagged.

```python
from archetype import rule
from archetype.rules import deprecated

@rule("legacy-billing-removed")
def legacy_billing_removed() -> None:
    deprecated(
        "myapp.legacy_billing",
        sunset="2027-06-30",
        reason="replaced by myapp.billing_v2",
    )
```

```
Deprecated module import: 'myapp.reports' imports 'myapp.legacy_billing', which
is deprecated (replaced by myapp.billing_v2). Scheduled for removal on
2027-06-30 (250 day(s) remaining).
```

`deprecated(...)` always reports a violation when the module is imported — it does not decide pass/fail from the date itself, keeping severity policy in one place. Combine it with [`@escalate`](#gradual-severity-escalation) to make it warn now and start failing the build exactly on `sunset`, with no second step to remember on the day:

```python
@rule("legacy-billing-removed")
@escalate(warn_until="2027-06-30")
def legacy_billing_removed() -> None:
    deprecated("myapp.legacy_billing", sunset="2027-06-30")
```

Both `sunset` and `reason` are optional; without `sunset` the message reports "No removal date is set."

## Gradual Severity Escalation

Rolling out a brand-new architecture rule org-wide as a hard failure on day
one blocks every pull request that happens to touch an existing violation
at once. `@escalate` schedules the transition instead: the rule is
warning-only up to a deadline, then becomes a hard failure automatically
from that date on, with no code or config change needed on the day itself.

```python
@rule("no-legacy-imports")
@escalate(warn_until="2027-06-30")
def no_legacy_imports() -> None:
    imports("myapp").must_not_import("myapp.legacy")
```

Through 2027-06-30 (inclusive), violations show up as warnings — visible
in output, but they don't fail the exit code, same as `@warn`. From
2027-07-01 onward, the same rule fails the build on any remaining
violation.

This differs from manually changing a rule's `archetype.toml` policy from
`"warning"` to `"error"` on the deadline: nobody has to remember to make
that edit, and every project depending on a [shared rule package](#shared-inheritable-rule-packs)
escalates on the same date without needing to coordinate the timing
themselves.

A rule currently in its warning period is shown with its deadline, for
example `no-legacy-imports (warn until 2027-06-30)`, and the deadline is
also included in JSON (`escalate_date`) and SARIF report output.

## Shared, Inheritable Rule Packs

Publish a set of rules as a normal installable Python package so multiple
repositories can enforce the same policy without copy-pasting
`architecture.py` between them:

```python
# In the shared package (e.g. acme_archetype_rules)
from archetype import group, imports, rule

with group("Org baseline"):
    @rule("no-direct-db-access-from-api")
    def no_direct_db_access_from_api() -> None:
        imports("api").must_not_import("db")
```

```python
# In each consuming project's architecture.py
import acme_archetype_rules
from archetype.rule import use

use(acme_archetype_rules)
```

`use()` registers every `@rule`-decorated function found in a module (or
accepts individual rule functions, or an iterable of them). Unlike a bare
`import`, it's safe to call even when the shared module was already
imported earlier in the same process — for example, a monorepo's pytest
plugin collecting multiple `architecture.py` files against the same shared
package — because Python only re-executes a module's `@rule` decorators
the first time it's imported.

A repository can still relax or disable one inherited rule locally without
touching the shared package, using the normal per-rule `policy` setting in
`archetype.toml`, matched by the rule's name:

```toml
[rules."no-direct-db-access-from-api"]
policy = "warning"
```

See [`examples/shared-rules/`](../examples/shared-rules) for a complete,
runnable example.
