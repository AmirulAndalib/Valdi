// for-of and for-in (both must live inside a function for the compiler to accept for-in).
export function iterate(items: number[]): number {
  let sum = 0;
  for (const item of items) {
    sum += item;
  }

  const obj: { [key: string]: number } = { x: 1, y: 2 };
  for (const key in obj) {
    sum += obj[key];
  }

  return sum;
}
