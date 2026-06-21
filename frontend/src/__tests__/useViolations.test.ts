import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import api from '../api/client';
import { useViolations } from '../hooks/useViolations';

vi.mock('../api/client', () => ({ default: { get: vi.fn() } }));

describe('useViolations', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockResolvedValue({
      data: { total_count: 0, page: 1, page_size: 20, results: [] },
    });
  });

  it('loads violations on mount', async () => {
    const { result } = renderHook(() => useViolations());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.get).toHaveBeenCalledWith('/violations', expect.any(Object));
  });
});
