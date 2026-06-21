import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import UploadPage from '../pages/UploadPage';

vi.mock('../hooks/useUpload', () => ({
  useUpload: () => ({ upload: vi.fn(), status: 'idle', result: null, error: null }),
}));

describe('UploadPage', () => {
  it('renders dropzone', () => {
    render(<MemoryRouter><UploadPage /></MemoryRouter>);
    expect(screen.getByText(/Upload Image/i)).toBeInTheDocument();
    expect(screen.getByText(/Drag & drop/i)).toBeInTheDocument();
  });
});
