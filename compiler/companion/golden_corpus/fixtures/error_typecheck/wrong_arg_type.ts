// Call a function with an argument of the wrong type. Pins the TS2345 diagnostic.
function greet(name: string): string {
  return 'hi ' + name;
}

export const greeting = greet(42);
