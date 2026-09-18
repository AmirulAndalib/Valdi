// Access a property that does not exist on the type. Pins the TS2339 diagnostic.
interface Point {
  x: number;
  y: number;
}

export function sum(p: Point): number {
  return p.x + p.z;
}
