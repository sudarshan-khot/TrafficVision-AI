import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ViolationsListPage from '../pages/ViolationsListPage';

vi.mock('../hooks/useViolations', () => ({
  useViolations: () => ({
    violations: [],
    totalCount: 0,
    loading: false,
    error: null,
    filters: { page: 1, page_size: 20 },
    setFilters: vi.fn(),
    setPage: vi.fn(),
  }),
}));

describe('ViolationsListPage', () => {
  it('renders filter bar and empty state', () => {
    render(<MemoryRouter><ViolationsListPage /></MemoryRouter>);
    expect(screen.getByText('Violations')).toBeInTheDocument();
    expect(screen.getByText('No violations found')).toBeInTheDocument();
  });
});
