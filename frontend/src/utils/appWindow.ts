// The Mac app's own window. pywebview gives its page window.pywebview.api
// (desktop/desktop_api.py) just after the page loads, then fires
// "pywebviewready"; a browser never has it.

/** The window's API, or null outside the Mac app's window (or before pywebview has added it). */
export function appWindowApi(): PyWebViewAPI | null {
  return window.pywebview?.api ?? null;
}

/**
 * Calls back with the window's API once pywebview has added it: at once
 * when it is already there, else on "pywebviewready". Returns what stops
 * listening.
 */
export function onAppWindowApi(callback: (api: PyWebViewAPI) => void): () => void {
  const ready = () => {
    const api = appWindowApi();
    if (api) callback(api);
  };
  ready();
  window.addEventListener("pywebviewready", ready);
  return () => window.removeEventListener("pywebviewready", ready);
}
