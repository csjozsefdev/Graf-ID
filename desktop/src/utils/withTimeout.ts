/** Bounds how long the UI will wait on an IPC call before treating it as failed.
 *
 * Without this, a hung Python subprocess (or Tauri command) can leave a busy flag
 * set forever — the "Open Project" button stuck on "Opening…", or the window-close
 * handler permanently refusing to close because `closeSessionBusy` never clears
 * (H7, H8). `withTimeout` never cancels the underlying call (Tauri/IPC offers no
 * cancellation), it only stops the *caller* from waiting past `ms` — if the real
 * call eventually settles after the timeout, its result is simply discarded.
 */

export class TimeoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TimeoutError";
  }
}

export function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new TimeoutError(`timeout: ${message}`));
    }, ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (err) => {
        clearTimeout(timer);
        reject(err);
      }
    );
  });
}
