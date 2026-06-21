import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DashboardPage from '../pages/DashboardPage';

vi.mock('../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    analytics: { total: 10, by_type: { HELMET_NON_COMPLIANCE: 10 }, by_date: [{ date: '2024-01-01', count: 5 }] },
    loading: false,
    error: null,
  }),
}));

vi.mock('../hooks/useViolations', () => ({
  useViolations: () => ({
    violations: [{ id: '1', violation_type: 'HELMET_NON_COMPLIANCE', plate_number: 'MH12DE1433', created_at: '2024-01-01' }],
    loading: false,
    error: null,
  }),
}));

describe('DashboardPage', () => {
  it('renders summary and recent violations', () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Total Violations')).toBeInTheDocument();
    expect(screen.getByText('Recent Violations')).toBeInTheDocument();
  });
});
