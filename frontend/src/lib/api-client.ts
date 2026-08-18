import axios from "axios";

const defaultApiBaseUrl = "http://localhost:3001/api/v1";

export const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL?.trim() || defaultApiBaseUrl
).replace(/\/+$/, "");

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
});
