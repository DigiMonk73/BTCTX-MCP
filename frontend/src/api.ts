import axios from "axios";
import { API_BASE_URL } from "./config";

// Every request says which page sent it (2.0 spec 5.13): the server refuses a
// browser's change from a page older than 2.0, which would save a Buy or Sell
// into the first exchange
const PAGE_HEADERS = { "X-BitcoinTX-Page": __BTCTX_VERSION__ };

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // Include session cookie in all requests
  headers: PAGE_HEADERS,
});

export async function downloadPdfWithAxios(
  url: string,
  onProgress?: (percent: number) => void
): Promise<Blob> {
  const response = await axios.get(url, {
    responseType: "blob",
    headers: PAGE_HEADERS,
    onDownloadProgress: (evt) => {
      if (evt.total && onProgress) {
        const percent = Math.floor((evt.loaded / evt.total) * 100);
        onProgress(percent);
      }
    },
  });
  return response.data; // This is your PDF blob
}

export default api;
