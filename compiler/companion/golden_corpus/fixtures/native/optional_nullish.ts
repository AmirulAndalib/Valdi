// Optional property/element/call chaining and nullish coalescing.
interface Config {
  timeout?: number;
  nested?: { retries?: number };
  handlers?: (() => void)[];
}

export function resolve(config: Config | undefined): number {
  const timeout = config?.timeout ?? 30;
  const retries = config?.nested?.retries ?? 3;
  const first = config?.handlers?.[0];
  const value = config?.timeout ?? timeout;
  return timeout + retries + (first ? 1 : 0) + value;
}
