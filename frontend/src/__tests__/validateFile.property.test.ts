import { describe, expect, it } from 'vitest';
import * as fc from 'fast-check';
import { validateFile } from '../hooks/useUpload';

describe('validateFile property', () => {
  it('rejects all invalid files (Property 12)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 20 * 1024 * 1024 + 1, max: 50 * 1024 * 1024 }),
        fc.constantFrom('image/gif', 'application/pdf', 'text/plain'),
        (size, type) => {
          const file = new File(['x'], 'f', { type });
          Object.defineProperty(file, 'size', { value: size });
          expect(validateFile(file)).not.toBeNull();
        },
      ),
    );
  });

  it('accepts valid jpeg and png', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 20 * 1024 * 1024 }),
        fc.constantFrom('image/jpeg', 'image/png'),
        (size, type) => {
          const file = new File(['x'], 'f', { type });
          Object.defineProperty(file, 'size', { value: size });
          expect(validateFile(file)).toBeNull();
        },
      ),
    );
  });
});
