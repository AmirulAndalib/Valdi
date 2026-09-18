// Destructuring as an assignment (not declaration): array with hole + rest,
// object assignment, and a default value.
export function rearrange(arr: number[], obj: { a: number; b: number }): number {
  let x = 0;
  let y = 0;
  let z = 0;
  [x, , y] = arr;

  let rest: number[] = [];
  [z, ...rest] = arr;

  let a = 0;
  let b = 0;
  ({ a, b } = obj);

  let first = 0;
  [first = 99] = arr;

  return x + y + z + a + b + first + rest.length;
}
