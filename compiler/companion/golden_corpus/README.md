# Compiler emit goldens (Tier 2, in-process)

Fixtures and checked-in expected output for the in-process compiler-emit golden
test, `../src/golden.spec.ts`. It compiles each fixture through the companion's
own compile API (`JSXProcessor` for web JS, `NativeCompiler` for native C) and
diffs the result against the golden here — the fast, in-process counterpart to
the Bazel-driven `tools/ci/compiler_golden_test.sh` (Tier 1). It exists to catch
silent emitter changes, most importantly from a TypeScript dependency bump.

## Layout
- `fixtures/web/*.tsx` → compiled to web JS, golden `expected/web/<name>.js.golden`
- `fixtures/native/*.ts` → compiled to native C, golden `expected/native/<name>.c.golden`

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
The seed corpus is intentionally small and does not yet exercise the whole
emitter. Known gaps to fill with targeted fixtures:
- The `NativeCompiler` C emitter has the lowest branch coverage of the emitters;
  add native fixtures for the branches it misses (control flow, exceptions,
  async, classes/inheritance, closures).
- More `EmitResolver` constant-resolution cases (const enums, cross-const refs).
- Broader web/JSX shapes (conditionals, lists, view models, attributes).

Expanding the corpus is tracked as a follow-up alongside measuring the emitter's
real coverage; see the TypeScript-upgrade plan.
