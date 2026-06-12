import { describe, expect, it } from 'vitest';
import { parseApiError } from '../error';

describe('parseApiError', () => {
  it('redacts sensitive values from raw messages', () => {
    const parsed = parseApiError({
      response: {
        status: 500,
        data: {
          detail: {
            message: 'request failed with Authorization: Bearer sk-secret123 and api_key=abc123',
          },
        },
      },
    });

    expect(parsed.rawMessage).toContain('Bearer [REDACTED]');
    expect(parsed.rawMessage).toContain('api_key=[REDACTED]');
    expect(parsed.rawMessage).not.toContain('sk-secret123');
    expect(parsed.rawMessage).not.toContain('abc123');
  });
});
