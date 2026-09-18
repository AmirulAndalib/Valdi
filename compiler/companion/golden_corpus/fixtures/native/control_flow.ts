// if/else-if/else, while, do/while, for, break, continue, ternary.
export function classify(n: number): string {
  let result = '';
  if (n < 0) {
    result = 'negative';
  } else if (n === 0) {
    result = 'zero';
  } else {
    result = 'positive';
  }

  let i = 0;
  while (i < n) {
    if (i === 5) {
      break;
    }
    i++;
  }

  let j = 0;
  do {
    j++;
  } while (j < 3);

  for (let k = 0; k < n; k++) {
    if (k % 2 === 0) {
      continue;
    }
    result = result + 'x';
  }

  return n > 10 ? 'big' : result;
}
