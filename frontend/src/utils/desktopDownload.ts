/**
 * FILE: frontend/src/utils/desktopDownload.ts
 *
 * Desktop-aware file download utility for pywebview integration.
 *
 * In browser mode, uses standard anchor download. In desktop mode
 * (pywebview), uses native macOS save dialog via the Python API.
 */

/**
 * Result of a download operation
 */
export interface DownloadResult {
  success: boolean;
  path?: string;
  error?: string;
}

/**
 * Check if running in pywebview desktop mode
 */
export function isDesktopApp(): boolean {
  return typeof window.pywebview !== "undefined";
}

/**
 * Convert a Blob to base64 string
 */
async function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      // Result is "data:application/pdf;base64,XXXX..." - extract just the base64 part
      const result = reader.result as string;
      const base64 = result.split(",")[1];
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

/**
 * Download a file in browser mode using anchor element
 */
function downloadInBrowser(blob: Blob, filename: string): DownloadResult {
  const blobUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(blobUrl);
  return { success: true };
}

/**
 * Download a file using desktop native save dialog
 */
async function downloadInDesktop(
  blob: Blob,
  filename: string,
  fileType: "pdf" | "csv" | "btx"
): Promise<DownloadResult> {
  const api = window.pywebview?.api;
  if (!api) {
    // Fallback to browser mode if API not available
    return downloadInBrowser(blob, filename);
  }

  try {
    const base64Data = await blobToBase64(blob);
    const result = await api.save_file(filename, base64Data, fileType);
    return result;
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : "Unknown error",
    };
  }
}

/**
 * Download a file with automatic desktop/browser detection
 *
 * @param blob - File content as Blob
 * @param filename - Suggested filename
 * @param fileType - File type (pdf or csv)
 * @returns Download result with success status and optional path/error
 */
export async function downloadFile(
  blob: Blob,
  filename: string,
  fileType: "pdf" | "csv" | "btx"
): Promise<DownloadResult> {
  if (isDesktopApp()) {
    return downloadInDesktop(blob, filename, fileType);
  } else {
    return downloadInBrowser(blob, filename);
  }
}

/**
 * Save a download and say how it went: where the Mac app saved it, or that
 * it downloaded; why saving failed; null when the user cancelled the save.
 */
export async function downloadMessage(
  blob: Blob,
  filename: string,
  fileType: "pdf" | "csv" | "btx",
  what: string
): Promise<string | null> {
  const result = await downloadFile(blob, filename, fileType);
  if (result.success) {
    return isDesktopApp() && result.path ? `${what} saved to: ${result.path}` : `${what} downloaded.`;
  }
  if (result.error && result.error !== "Save cancelled") {
    return `Save failed: ${result.error}`;
  }
  return null;
}
