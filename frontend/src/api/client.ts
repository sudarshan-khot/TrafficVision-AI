import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
});

export function fixMinioUrl(url: string | null | undefined): string {
  if (!url) return '';
  return url.replace('//minio:9000', '//localhost:9000');
}

export default api;
