import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ViolationDetailPage from '../pages/ViolationDetailPage';
import api from '../api/client';

vi.mock('../api/client', () => ({
  default: { get: vi.fn() },
}));

describe('ViolationDetailPage', () => {
  it('shows not found on error', async () => {
    vi.mocked(api.get).mockRejectedValue(new Error('404'));
    render(
      <MemoryRouter initialEntries={['/violations/bad-id']}>
        <Routes>
          <Route path="/violations/:id" element={<ViolationDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Violation not found' })).toBeInTheDocument());
  });
});
