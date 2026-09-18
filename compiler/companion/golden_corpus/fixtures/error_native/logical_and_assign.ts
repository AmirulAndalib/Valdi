// Logical-AND assignment (&&=) is type-valid but unsupported by the native
// lowering (only ??= and ||= are handled), so this throws NativeCompilerError.
export function applyAnd(a: boolean, b: boolean): boolean {
  let result = a;
  result &&= b;
  return result;
}
