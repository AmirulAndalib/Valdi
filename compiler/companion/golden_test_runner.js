/**
 * Runs the compiled compiler-emit golden spec under Jest (Tier 2).
 *
 * golden.spec.ts is compiled to golden.spec.js by the :golden_spec ts_project;
 * this entry runs plain Jest (no ts-jest transform) on that compiled JS,
 * resolving the companion's node_modules and the golden corpus from runfiles.
 * Modeled on src/valdi_modules/src/valdi/coreutils/web/test/run_tests.js.
 */

const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const runfiles = process.env.RUNFILES_DIR || process.env.RUNFILES;
if (!runfiles) {
  console.error('RUNFILES_DIR not set');
  process.exit(1);
}

// Runfiles are rooted at "_main" when this workspace is built directly, and under the valdi
// repo name when another workspace consumes it through bzlmod.
const workspacePrefixes = ['_main', 'valdi', '+local_repos+valdi'];

function resolveInRunfiles(relativePath) {
  for (const prefix of workspacePrefixes) {
    const candidate = path.join(runfiles, prefix, relativePath);
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

const nodeModulesPath = resolveInRunfiles('compiler/companion/node_modules');
if (!nodeModulesPath) {
  console.error(`Could not find companion node_modules under ${runfiles}`);
  process.exit(1);
}

process.env.NODE_PATH = nodeModulesPath + (process.env.NODE_PATH ? ':' + process.env.NODE_PATH : '');
require('module').Module._initPaths();

const jestBin = path.join(nodeModulesPath, 'jest/bin/jest.js');
if (!fs.existsSync(jestBin)) {
  console.error(`Jest binary not found at: ${jestBin}`);
  process.exit(1);
}

const specJs = resolveInRunfiles('compiler/companion/src/golden.spec.js');
if (!specJs) {
  console.error(`Compiled golden.spec.js not found under ${runfiles}`);
  process.exit(1);
}
const testDir = path.dirname(specJs);

// Regeneration mode: `UPDATE_GOLDENS=1 bazel run //compiler/companion:golden_update`
// points the corpus at the source tree (BUILD_WORKSPACE_DIRECTORY, set by
// `bazel run`) so refreshed goldens are written back to source, not the sandbox.
// Verify mode (bazel test) reads the corpus from runfiles.
if (process.env.UPDATE_GOLDENS && process.env.BUILD_WORKSPACE_DIRECTORY) {
  process.env.GOLDEN_CORPUS_DIR = path.join(
    process.env.BUILD_WORKSPACE_DIRECTORY,
    'compiler/companion/golden_corpus',
  );
} else {
  const corpusDir = resolveInRunfiles('compiler/companion/golden_corpus');
  if (!corpusDir) {
    console.error(`golden_corpus not found under ${runfiles}`);
    process.exit(1);
  }
  process.env.GOLDEN_CORPUS_DIR = corpusDir;
}

// An explicit config keeps Jest from discovering the other companion specs and
// from applying the repo's ts-jest preset to already-compiled JS. Write it to a
// writable scratch dir (Bazel sets TEST_TMPDIR for tests; os.tmpdir() covers
// `bazel run` and local runs) since the runfiles tree can be read-only.
const configPath = path.join(
  process.env.TEST_TMPDIR || require('os').tmpdir(),
  `jest.golden.config.${process.pid}.json`,
);
fs.writeFileSync(
  configPath,
  JSON.stringify({
    testEnvironment: 'node',
    roots: [testDir],
    testMatch: ['**/golden.spec.js'],
  }),
);

console.log('Running golden spec:', specJs);
console.log('GOLDEN_CORPUS_DIR:', process.env.GOLDEN_CORPUS_DIR);
const result = spawnSync(process.execPath, [jestBin, '--config', configPath, '--verbose', '--runTestsByPath', specJs], {
  stdio: 'inherit',
  cwd: testDir,
});

try {
  fs.unlinkSync(configPath);
} catch {
  // Ignore cleanup failures; the sandbox is discarded anyway.
}

process.exit(result.status === null ? 1 : result.status);
