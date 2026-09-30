import axios from "axios";
import { API_BASE_URL } from "./config";

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // Include session cookie in all requests
});

export async function downloadPdfWithAxios(
  url: string,
  onProgress?: (percent: number) => void
): Promise<Blob> {
  const response = await axios.get(url, {
    responseType: "blob",
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
