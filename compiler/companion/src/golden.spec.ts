/**
 * In-process compiler emit goldens (Tier 2).
 *
 * Compiles each fixture under ../golden_corpus/fixtures through the companion's
 * own in-process compile API and diffs the emitted output against a checked-in
 * golden under ../golden_corpus/expected. This is the fast, in-process
 * counterpart to the Bazel-driven tools/ci/compiler_golden_test.sh (Tier 1):
 * it exercises the emitters directly (JSXProcessor for web JS, NativeCompiler
 * for native C) so a change in emitted output -- most importantly from a
 * TypeScript dependency bump -- fails here even without a full Bazel build.
 *
 * Fixtures live OUTSIDE src/ so they are not swept into the `lib` ts_project
 * (which globs src/**\/*.ts); this spec is a *.spec.ts, which the lib excludes.
 *
 * Run:       bazel test //compiler/companion:golden_test
 * Regenerate: UPDATE_GOLDENS=1 bazel run //compiler/companion:golden_update
 * (after an intended emit change; review the golden diff in your PR).
 */
import 'ts-jest';
import * as fs from 'fs';
import * as path from 'path';
import * as ts from 'typescript';
import { JSXProcessor } from './JSXProcessor';
import { trimAllLines } from './utils/StringUtils';
import { Workspace } from './Workspace';
import { compileFile } from './native/CompileNativeCommand';
import { compileIRsToC } from './native/NativeCompiler';
import { NativeCompilerOptions } from './native/NativeCompilerOptions';

// Local dev (`npm test`) resolves the corpus relative to this file; the Bazel
// js_test sets GOLDEN_CORPUS_DIR to the corpus location in runfiles.
const CORPUS = process.env.GOLDEN_CORPUS_DIR || path.join(__dirname, '..', 'golden_corpus');
const UPDATE = !!process.env.UPDATE_GOLDENS;

// A fixed option set that exercises the constant-folding path (EmitResolver),
// which is the emitter surface most sensitive to a TypeScript version bump.
const NATIVE_OPTIONS: NativeCompilerOptions = {
  optimizeSlots: true,
  optimizeVarRefs: true,
  foldConstants: true,
};

// The same fixtures compiled with every optimization OFF, so the unfolded /
// unoptimized emit -- a distinct EmitResolver / NativeCompiler path -- is pinned
// alongside the folded one. A TypeScript bump could regress either path
// independently.
const NATIVE_OPTIONS_UNOPT: NativeCompilerOptions = {
  optimizeSlots: false,
  optimizeVarRefs: false,
  foldConstants: false,
};

// Web/JSX path: pure source-string transpile, no Workspace or dependency
// resolution needed.
function compileWeb(src: string): string {
  return trimAllLines(JSXProcessor.createFromFile('File.jsx', src, false).process());
}

// An in-memory Workspace that type-checks against lib.es2015 only. rootPath '/'
// keeps the file reference in any diagnostic/error text relative to '/', so
// captured messages stay host-portable (no absolute path leaks).
function nativeWorkspace(src: string): Workspace {
  const workspace = new Workspace(
    '/',
    false,
    undefined,
    { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.CommonJS, lib: ['lib.es2015.d.ts'] },
    undefined,
  );
  workspace.registerInMemoryFile('file.ts', src);
  workspace.addSourceFileAtPath('file.ts');
  return workspace;
}

// Native path: compile through the in-memory Workspace to generated C.
function compileNativeWith(src: string, options: NativeCompilerOptions): string {
  const irs = compileFile(nativeWorkspace(src), true, options, 'file.ts', 'file.ts');
  return compileIRsToC(irs, options).source;
}
function compileNativeC(src: string): string {
  return compileNativeWith(src, NATIVE_OPTIONS);
}
function compileNativeCUnopt(src: string): string {
  return compileNativeWith(src, NATIVE_OPTIONS_UNOPT);
}

// --- Error / diagnostic goldens ------------------------------------------------
// Compile *invalid* input and pin the compiler's diagnostics / thrown message.
// A TypeScript bump routinely changes error wording, codes, and what's rejected;
// none of that is caught by the success-path goldens above.

// Type-check diagnostics: getDiagnosticsSync returns structured diagnostics and
// does NOT throw. Each `.text` is ts.formatDiagnostic output
// (`file.ts(line,col): error TSxxxx: ...`); the TSxxxx code + wording are the
// version-sensitive signal we want to pin.
function compileTypecheckDiagnostics(src: string): string {
  const result = nativeWorkspace(src).getDiagnosticsSync('file.ts');
  const body = result.diagnostics.map((d) => d.text.trimEnd()).join('\n');
  return `hasError=${result.hasError}\n${body}\n`;
}

// Native-lowering errors: an unsupported construct throws NativeCompilerError
// with a stable location-tagged message. syntaxCheck=false skips the type-check
// throw so we reach the lowering rather than stopping at a semantic error.
function compileNativeError(src: string): string {
  try {
    const irs = compileFile(nativeWorkspace(src), false, NATIVE_OPTIONS, 'file.ts', 'file.ts');
    compileIRsToC(irs, NATIVE_OPTIONS);
    return 'UNEXPECTED: native compile did not throw\n';
  } catch (e) {
    return `${(e as Error).message}\n`;
  }
}

interface GoldenCase {
  name: string;
  fixturePath: string;
  goldenPath: string;
  compile: (src: string) => string;
}

function collect(
  sub: string,
  srcExt: string,
  goldExt: string,
  compile: (s: string) => string,
  label: string = sub,
): GoldenCase[] {
  const dir = path.join(CORPUS, 'fixtures', sub);
  if (!fs.existsSync(dir)) {
    return [];
  }
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(srcExt))
    .sort()
    .map((f) => ({
      name: `${label}/${f}`,
      fixturePath: path.join(dir, f),
      goldenPath: path.join(CORPUS, 'expected', sub, f.slice(0, -srcExt.length) + goldExt),
      compile,
    }));
}

// Goldens carry a trailing .golden so no language formatter (clang-format,
// eslint) matches and rewrites these verbatim compiler outputs.
const cases: GoldenCase[] = [
  ...collect('web', '.tsx', '.js.golden', compileWeb),
  ...collect('native', '.ts', '.c.golden', compileNativeC),
  // Optimization-off variant of the same native fixtures (pins the unfolded path).
  ...collect('native', '.ts', '.unopt.c.golden', compileNativeCUnopt, 'native-unopt'),
  // Error goldens: invalid inputs, capturing diagnostics / thrown messages.
  ...collect('error_typecheck', '.ts', '.diag.golden', compileTypecheckDiagnostics),
  ...collect('error_native', '.ts', '.err.golden', compileNativeError),
];

describe('compiler emit goldens (in-process)', () => {
  it('discovers fixtures', () => {
    expect(cases.length).toBeGreaterThan(0);
  });

  for (const c of cases) {
    it(c.name, () => {
      const src = fs.readFileSync(c.fixturePath, 'utf8');
      const actual = c.compile(src);
      if (UPDATE) {
        fs.mkdirSync(path.dirname(c.goldenPath), { recursive: true });
        fs.writeFileSync(c.goldenPath, actual);
        return;
      }
      if (!fs.existsSync(c.goldenPath)) {
        throw new Error(`Missing golden ${c.goldenPath}. Seed with: UPDATE_GOLDENS=1 npx jest src/golden.spec.ts`);
      }
      expect(actual).toBe(fs.readFileSync(c.goldenPath, 'utf8'));
    });
  }
});
