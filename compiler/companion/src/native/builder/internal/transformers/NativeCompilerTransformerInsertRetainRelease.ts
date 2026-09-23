import { NativeCompilerBuilderVariableID } from '../../INativeCompilerBuilder';
import { NativeCompilerIR } from '../../NativeCompilerBuilderIR';
import { JumpIndexer } from './utils/JumpIndexer';
import { isBaseWithReturn } from './utils/IRVisitors';

function insertFreeIfNeeded(
  value: NativeCompilerBuilderVariableID,
  lastIR: NativeCompilerIR.Base | undefined,
  outputIRs: NativeCompilerIR.Base[],
): boolean {
  if (!value.isRetainable()) {
    return false;
  }

  if (lastIR && lastIR.kind === NativeCompilerIR.Kind.Free && (lastIR as NativeCompilerIR.Free).value === value) {
    // We just had a free before, no need to insert a release it
    return false;
  }

  const release: NativeCompilerIR.Free = {
    kind: NativeCompilerIR.Kind.Free,
    value: value,
  };
  outputIRs.push(release);
  return true;
}

export namespace NativeCompilerTransformerInsertRetainRelease {
  export function transform(
    startFunctionIR: NativeCompilerIR.StartFunction,
    irs: NativeCompilerIR.Base[],
    endFunctionIR: NativeCompilerIR.EndFunction,
  ): NativeCompilerIR.Base[] {
    // Keep an array of boolean where each index tells
    // whether the IR is reentrant, meaning that it is
    // possible that the IR gets evaluated multiple times
    // at runtime. We use this to know whether we should insert an additional
    // free before the instruction.
    const reentrantIRIndexes: boolean[] = [];

    // Keep track of assigned variables (by variable id).
    // There is no need to emit a release before the first assignment; on a
    // reassignment we must release the previous value first. A Set is used for
    // membership: a number[] tested with `in` checks array *indices*, not
    // values, so a variable whose id exceeded the count of distinct assigned
    // variables had its release skipped (a leak).
    const assignedVariables = new Set<number>();

    for (let i = 0; i < irs.length; i++) {
      reentrantIRIndexes.push(false);
    }

    const jumpIndexer = new JumpIndexer(irs);
    jumpIndexer.forEachBackwardJump((jumpIRIndex, irIndex) => {
      for (let i = jumpIRIndex; i < irIndex; i++) {
        reentrantIRIndexes![i] = true;
      }
    });

    let retval: NativeCompilerIR.Base[] = [];
    const releaseIRs: NativeCompilerIR.Free[] = [];

    let lastIR: NativeCompilerIR.Base | undefined;
    let irIndex = 0;
    for (const ir of irs) {
      switch (ir.kind) {
        case NativeCompilerIR.Kind.Slot:
          {
            let typedIR = ir as NativeCompilerIR.Slot;

            if (typedIR.value.isRetainable()) {
              const release: NativeCompilerIR.Free = {
                kind: NativeCompilerIR.Kind.Free,
                value: typedIR.value,
              };
              releaseIRs.push(release);
            }

            retval.push(ir);
          }
          break;
        case NativeCompilerIR.Kind.Assignment:
          {
            let typedIR = ir as NativeCompilerIR.Assignment;

            const assigned = assignedVariables.has(typedIR.left.variable);
            if (!assigned) {
              // record first assign
              assignedVariables.add(typedIR.left.variable);
            }
            // skip release when safe
            // 1. not assigned
            // 2. not in reentrant region
            if (assigned || reentrantIRIndexes[irIndex]) {
              insertFreeIfNeeded(typedIR.left, lastIR, retval);
            }

            retval.push(typedIR);

            if (typedIR.right.isRetainable()) {
              const retain: NativeCompilerIR.Retain = {
                kind: NativeCompilerIR.Kind.Retain,
                value: typedIR.left,
              };
              retval.push(retain);
            }
          }
          break;
        default: {
          if (isBaseWithReturn(ir) && !assignedVariables.has(ir.variable.variable)) {
            // record first assign
            assignedVariables.add(ir.variable.variable);
          }
          if (reentrantIRIndexes[irIndex] && isBaseWithReturn(ir)) {
            // Our IR is re-entrant, so we should insert a free before
            // assigning the variable
            insertFreeIfNeeded(ir.variable, lastIR, retval);
          }

          retval.push(ir);
        }
      }

      irIndex++;
      lastIR = ir;
    }

    // Release in the reverse order in which they were declared
    releaseIRs.reverse();

    return [...retval, ...releaseIRs];
  }
}
