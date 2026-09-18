// Arrays, objects, array/object destructuring + rest, spread, template literals.
export function transform(): number {
  const nums = [1, 2, 3, 4];
  const [first, second, ...rest] = nums;
  const obj = { a: 1, b: 2, c: 3 };
  const { a, ...others } = obj;
  const merged = { ...obj, d: 4 };
  const combined = [0, ...nums, 5];
  const name = 'valdi';
  const label = `name=${name} first=${first}`;
  return (
    first +
    second +
    rest.length +
    a +
    merged.d +
    combined.length +
    label.length +
    Object.keys(others).length
  );
}
