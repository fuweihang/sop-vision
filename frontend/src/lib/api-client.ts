import axios from "axios";

const DEFAULT_API_BASE_URL = "http://localhost:3001/api/v1";

export const apiBaseUrl =
  import.meta.env.VITE_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL;

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
});
