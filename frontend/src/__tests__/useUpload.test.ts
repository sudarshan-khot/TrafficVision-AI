import { describe, expect, it } from 'vitest';
import { validateFile } from '../hooks/useUpload';

describe('validateFile', () => {
  it('accepts valid jpeg', () => {
    const file = new File(['x'], 'test.jpg', { type: 'image/jpeg' });
    Object.defineProperty(file, 'size', { value: 1024 });
    expect(validateFile(file)).toBeNull();
  });

  it('rejects oversized files', () => {
    const file = new File(['x'], 'big.jpg', { type: 'image/jpeg' });
    Object.defineProperty(file, 'size', { value: 21 * 1024 * 1024 });
    expect(validateFile(file)).toBeTruthy();
  });

  it('rejects invalid mime type', () => {
    const file = new File(['x'], 'test.gif', { type: 'image/gif' });
    Object.defineProperty(file, 'size', { value: 1024 });
    expect(validateFile(file)).toBeTruthy();
  });
});
