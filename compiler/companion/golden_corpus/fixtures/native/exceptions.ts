// throw, try/catch/finally.
export function risky(input: number): string {
  const log: string[] = [];
  try {
    if (input < 0) {
      throw new Error('negative');
    }
    log.push('ok');
  } catch (e) {
    log.push('caught');
  } finally {
    log.push('done');
  }
  return log.join(',');
}
