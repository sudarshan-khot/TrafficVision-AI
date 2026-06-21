import { useCallback, useEffect, useState } from 'react';
import api from '../api/client';
import type { ViolationFilters, ViolationRecord, ViolationsListResponse } from '../types';

export function useViolations(initial: ViolationFilters = {}) {
  const [filters, setFilters] = useState<ViolationFilters>({
    page: 1,
    page_size: 20,
    ...initial,
  });
  const [violations, setViolations] = useState<ViolationRecord[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchViolations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<ViolationsListResponse>('/violations', { params: filters });
      setViolations(res.data.results);
      setTotalCount(res.data.total_count);
    } catch {
      setError('Failed to load violations');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchViolations();
  }, [fetchViolations]);

  const setPage = (page: number) => setFilters((f) => ({ ...f, page }));

  return { violations, totalCount, loading, error, filters, setFilters, setPage, refetch: fetchViolations };
}
