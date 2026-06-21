import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AnalyticsPage from '../pages/AnalyticsPage';

vi.mock('../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    analytics: null,
    loading: false,
    error: null,
    startDate: '2024-01-01',
    endDate: '2024-01-31',
    setDateRange: vi.fn(),
  }),
}));

describe('AnalyticsPage', () => {
  it('renders date range picker', () => {
    render(<MemoryRouter><AnalyticsPage /></MemoryRouter>);
    expect(screen.getByText('Analytics')).toBeInTheDocument();
    expect(screen.getByText('Start')).toBeInTheDocument();
  });
});
