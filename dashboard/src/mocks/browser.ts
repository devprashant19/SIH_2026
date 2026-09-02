// Mock Service Worker bootstrap for `npm run dev:mock`. Handlers live in src/mocks/handlers.ts;
// an empty handler list is valid.
export async function startMocks(): Promise<void> {
  const { setupWorker } = await import("msw/browser");
  const { handlers } = await import("./handlers");
  const worker = setupWorker(...handlers);
  await worker.start({ onUnhandledRequest: "bypass" });
}
