import axios from "axios";

const DEFAULT_API_BASE_URL = "http://localhost:3001/api/v1";
const INVALID_API_BASE_URL_MESSAGE =
  "VITE_API_BASE_URL 必须是有效的绝对 HTTP(S) URL";
const ABSOLUTE_HTTP_URL_PATTERN = /^https?:\/\//i;

export function resolveApiBaseUrl(value: string | undefined): string {
  const baseUrl = value?.trim() || DEFAULT_API_BASE_URL;

  let parsedUrl: URL;

  try {
    parsedUrl = new URL(baseUrl);
  } catch {
    throw new Error(INVALID_API_BASE_URL_MESSAGE);
  }

  if (
    (parsedUrl.protocol !== "http:" && parsedUrl.protocol !== "https:") ||
    !ABSOLUTE_HTTP_URL_PATTERN.test(baseUrl)
  ) {
    throw new Error(INVALID_API_BASE_URL_MESSAGE);
  }

  return baseUrl;
}

export const apiBaseUrl = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL);

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
});
