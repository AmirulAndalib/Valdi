import type { NativeMessageEvent, NativeMessagePort } from 'valdi_core/src/ValdiRuntime';

onmessage = workerEvent => {
  const event = workerEvent as unknown as NativeMessageEvent<unknown>;
  const port: NativeMessagePort = event.ports[0];

  // Acknowledge over the transferred port so the host knows the worker is running, then spin forever.
  // The host terminates the worker while this loop is executing.
  port.postMessage('ready');

  while (true) {}
};
