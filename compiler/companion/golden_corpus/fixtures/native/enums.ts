// Numeric enum (auto-increment), computed const enum, string enum (EmitResolver).
enum Direction {
  North,
  East,
  South,
  West,
}

const enum Flags {
  None = 0,
  Read = 1,
  Write = 2,
  ReadWrite = Read | Write,
}

enum Level {
  Low = 'low',
  High = 'high',
}

export function navigate(): number {
  const d = Direction.East;
  const f = Flags.ReadWrite;
  const l = Level.High;
  return d + f + l.length;
}
