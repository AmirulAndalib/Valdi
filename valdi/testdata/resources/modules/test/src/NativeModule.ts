import { makeCalculator } from './NativeCalculator';

export function compute(): number {
  const calculator = makeCalculator();
  calculator.add(42);
  calculator.add(8);
  return calculator.total();
}

let syncCallCount = 0;

// Counts how many times native actually ran this function, so tests can tell a call that was
// skipped after its deadline from one that ran late.
export function countSyncCall(): number {
  syncCallCount++;
  return syncCallCount;
}
