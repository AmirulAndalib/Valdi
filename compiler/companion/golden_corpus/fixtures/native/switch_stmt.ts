// switch with fall-through cases, default, break.
export function dayKind(day: number): string {
  let name: string;
  switch (day) {
    case 0:
    case 6:
      name = 'weekend';
      break;
    case 1:
    case 2:
    case 3:
    case 4:
    case 5:
      name = 'weekday';
      break;
    default:
      name = 'unknown';
      break;
  }
  return name;
}
