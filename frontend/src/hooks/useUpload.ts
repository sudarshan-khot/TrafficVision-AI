import { useCallback, useState } from 'react';
import api from '../api/client';
import type { AnalyzeResponse, UploadResponse } from '../types';

export type UploadStatus =
  | 'idle'
  | 'validating'
  | 'uploading'
  | 'analyzing'
  | 'success'
  | 'error';

const MAX_BYTES = 20 * 1024 * 1024;
const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png']);

export function validateFile(file: File): string | null {
  if (file.size > MAX_BYTES) {
    return 'File size exceeds 20 MB limit';
  }
  if (!ALLOWED_TYPES.has(file.type)) {
    return 'Only JPEG and PNG images are accepted';
  }
  return null;
}

export function useUpload() {
  const [status, setStatus] = useState<UploadStatus>('idle');
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const upload = useCallback(async (file: File) => {
    setError(null);
    setResult(null);
    setStatus('validating');
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      setStatus('error');
      return;
    }

    try {
      setStatus('uploading');
      const form = new FormData();
      form.append('file', file);
      const uploadRes = await api.post<UploadResponse>('/upload-image', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      setStatus('analyzing');
      const analyzeRes = await api.post<AnalyzeResponse>('/analyze', {
        image_id: uploadRes.data.image_id,
        object_path: uploadRes.data.object_path,
      });

      setResult(analyzeRes.data);
      setStatus('success');
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Upload or analysis failed';
      setError(String(message));
      setStatus('error');
    }
  }, []);

  return { upload, status, result, error };
}
