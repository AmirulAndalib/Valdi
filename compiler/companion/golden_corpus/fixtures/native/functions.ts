// Recursion, default params, higher-order functions, arrow closures.
function factorial(n: number): number {
  return n <= 1 ? 1 : n * factorial(n - 1);
}

function greet(name: string, greeting: string = 'Hello'): string {
  return greeting + ', ' + name;
}

function apply(fn: (x: number) => number, value: number): number {
  return fn(value);
}

function makeAdder(amount: number): (x: number) => number {
  return (x) => x + amount;
}

export function run(): number {
  const add5 = makeAdder(5);
  const doubled = apply((x) => x * 2, 10);
  return factorial(4) + add5(doubled) + greet('World').length;
}
