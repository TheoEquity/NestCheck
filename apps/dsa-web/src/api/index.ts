import axios from 'axios';
import { API_BASE_URL } from '../utils/constants';
import { attachParsedApiError } from './error';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const path = window.location.pathname + window.location.search;
      if (!path.startsWith('/login')) {
        const redirect = encodeURIComponent(path);
        window.location.assign(`/login?redirect=${redirect}`);
      }
    }
    attachParsedApiError(error);
    return Promise.reject(error);
  }
);

export default apiClient;

export async function apiRequest(path: string, options: RequestInit & { body?: string } = {}): Promise<any> {
  const url = API_BASE_URL + path;
  const resp = await fetch(url, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    body: options.body,
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    const err: any = new Error(data.message || data.error || 'Request failed');
    err.status = resp.status;
    err.response = { data, status: resp.status };
    attachParsedApiError(err);
    throw err;
  }
  return resp.status === 204 ? null : resp.json();
}
