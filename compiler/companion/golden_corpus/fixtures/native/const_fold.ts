// Exercises the constant-folding emitter path (EmitResolver.getConstantValue).
export function computed(): number {
  const a = 2;
  const b = 3;
  return a * b + 1;
}
