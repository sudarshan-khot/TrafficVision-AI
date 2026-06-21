import { useCallback, useEffect, useState } from 'react';
import { format, subDays } from 'date-fns';
import api from '../api/client';
import type { AnalyticsResponse } from '../types';

export function useAnalytics() {
  const [startDate, setStartDate] = useState(format(subDays(new Date(), 30), 'yyyy-MM-dd'));
  const [endDate, setEndDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalytics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<AnalyticsResponse>('/analytics', {
        params: { start_date: startDate, end_date: endDate },
      });
      setAnalytics(res.data);
    } catch {
      setError('Failed to load analytics');
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate]);

  useEffect(() => {
    fetchAnalytics();
  }, [fetchAnalytics]);

  const setDateRange = (start: string, end: string) => {
    setStartDate(start);
    setEndDate(end);
  };

  return { analytics, loading, error, startDate, endDate, setDateRange, refetch: fetchAnalytics };
}
