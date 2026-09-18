# Compiler emit goldens (Tier 2, in-process)

Fixtures and checked-in expected output for the in-process compiler-emit golden
test, `../src/golden.spec.ts`. It compiles each fixture through the companion's
own compile API (`JSXProcessor` for web JS, `NativeCompiler` for native C) and
diffs the result against the golden here — the fast, in-process counterpart to
the Bazel-driven `tools/ci/compiler_golden_test.sh` (Tier 1). It exists to catch
silent emitter changes, most importantly from a TypeScript dependency bump.

## Layout
- `fixtures/web/*.tsx` → compiled to web JS, golden `expected/web/<name>.js.golden`
- `fixtures/native/*.ts` → compiled to native C with all optimizations ON, golden
  `expected/native/<name>.c.golden`; the same fixtures are also compiled with all
  optimizations OFF into `expected/native/<name>.unopt.c.golden`, pinning the
  unfolded EmitResolver/NativeCompiler path alongside the folded one.
- `fixtures/error_typecheck/*.ts` → *invalid* input; the type-check diagnostics
  (`getDiagnosticsSync`) are captured into `expected/error_typecheck/<name>.diag.golden`.
- `fixtures/error_native/*.ts` → input the native lowering rejects; the thrown
  `NativeCompilerError` message is captured into `expected/error_native/<name>.err.golden`.

The error goldens pin the compiler's *diagnostics* (codes, wording, rejected
constructs) — a surface a TypeScript bump changes independently of successful
emit. A fixture that unexpectedly compiles produces an `UNEXPECTED: ...` golden,
which flags that it belongs elsewhere.

Goldens carry a `.golden` suffix so no language formatter (clang-format, eslint)
rewrites these verbatim compiler outputs.

## Running
```
bazel test //compiler/companion:golden_test
```

## Regenerating (after an intended emit change)
```
UPDATE_GOLDENS=1 bazel run //compiler/companion:golden_update
```
This writes refreshed goldens back into this directory. Review the resulting
golden diff in your PR.

## Adding a fixture
Drop a `.tsx` under `fixtures/web/` or a `.ts` under `fixtures/native/` (native
fixtures must type-check against `lib.es2015` alone — no external imports), then
regenerate. The runner discovers fixtures automatically.

## Coverage gaps (help wanted)
The corpus still does not exercise the whole emitter. Remaining gaps to fill:
- More `error_native` fixtures for other rejected constructs (only the `&&=`
  operator is pinned today).
- Web/JSX error goldens: `JSXProcessor.process()` throws on bad templates, but no
  `error_web` fixtures exist yet (the runner hook can be added the same way).
- More `EmitResolver` constant-resolution cases (const enums, cross-const refs,
  bigint / template-literal folding).
- Measuring the emitter's *real* branch coverage (needs an instrumented companion
  invoked by the swift driver, not just reasoned-missing fixtures).

Expanding the corpus is tracked in the TypeScript-upgrade plan.
