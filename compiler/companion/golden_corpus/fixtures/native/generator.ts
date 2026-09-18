// Generator function with yield inside a loop.
function* counter(max: number) {
  let i = 0;
  while (i < max) {
    yield i;
    i++;
  }
}

export function total(max: number): number {
  let sum = 0;
  for (const n of counter(max)) {
    sum += n;
  }
  return sum;
}
