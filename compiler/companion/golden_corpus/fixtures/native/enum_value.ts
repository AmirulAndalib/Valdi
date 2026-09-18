// Exercises enum constant resolution (EmitResolver) in the native emitter.
enum Color {
  Red = 1,
  Green = 2,
  Blue = 4,
}

export function pick(): number {
  return Color.Green | Color.Blue;
}
