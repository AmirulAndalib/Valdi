// Arithmetic, bitwise, shift, comparison, equality, logical, unary, typeof.
export function compute(a: number, b: number): number {
  const arith = a + b - (a * b) / (b + 1) + (a % 3) + a ** 2;
  const bitwise = (a & b) | (a ^ b);
  const shifts = (a << 1) + (a >> 1) + (a >>> 1);
  const cmp = (a < b ? 1 : 0) + (a > b ? 1 : 0) + (a <= b ? 1 : 0) + (a >= b ? 1 : 0);
  const eq = (a === b ? 1 : 0) + (a !== b ? 1 : 0);
  const logical = a && b ? b : a || b;
  const unary = -a + +b + ~a;
  const kind: string = typeof a;
  return arith + bitwise + shifts + cmp + eq + logical + unary + kind.length;
}
