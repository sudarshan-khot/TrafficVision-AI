import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import api from '../api/client';
import { useAnalytics } from '../hooks/useAnalytics';

vi.mock('../api/client', () => ({ default: { get: vi.fn() } }));

describe('useAnalytics', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockResolvedValue({
      data: { total: 0, by_type: {}, by_date: [], window_start: '', window_end: '', cached: false },
    });
  });

  it('fetches analytics with date params', async () => {
    const { result } = renderHook(() => useAnalytics());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.get).toHaveBeenCalledWith('/analytics', {
      params: { start_date: expect.any(String), end_date: expect.any(String) },
    });
  });
});
