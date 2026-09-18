// Nullish (??=) and logical-or (||=) compound assignment operators.
export function resolveOptions(input: { count?: number; name?: string }): number {
  let count = input.count;
  count ??= 10;

  let name = input.name;
  name ||= 'default';

  return count + name.length;
}
