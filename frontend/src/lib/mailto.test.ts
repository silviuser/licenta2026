import { describe, expect, it } from 'vitest';
import { buildMailto, formatAddressList, isMailtoWithinLimit } from './mailto';
import { MAILTO_MAX_URL } from './constants';

describe('buildMailto', () => {
  it('encodes the subject', () => {
    const url = buildMailto({ to: 'ana@x.com', subject: 'Role — next steps' });
    expect(url).toBe('mailto:ana%40x.com?subject=Role%20%E2%80%94%20next%20steps');
  });

  it('joins bcc recipients and omits the to field', () => {
    const url = buildMailto({ bcc: ['a@x.com', 'b@y.com'], subject: 'Hi' });
    expect(url).toContain('bcc=a%40x.com%2Cb%40y.com');
    expect(url.startsWith('mailto:?')).toBe(true);
  });

  it('drops empty bcc entries', () => {
    const url = buildMailto({ bcc: ['a@x.com', ''], subject: 'Hi' });
    expect(url).toContain('bcc=a%40x.com');
    expect(url).not.toContain('%2C'); // no trailing comma-encoded empty entry
  });

  it('produces a bare mailto when nothing is provided', () => {
    expect(buildMailto({})).toBe('mailto:');
  });
});

describe('isMailtoWithinLimit', () => {
  it('accepts short URLs and rejects ones past the practical limit', () => {
    expect(isMailtoWithinLimit('mailto:a@x.com')).toBe(true);
    expect(isMailtoWithinLimit('x'.repeat(MAILTO_MAX_URL + 1))).toBe(false);
  });
});

describe('formatAddressList', () => {
  it('comma-joins and skips blanks', () => {
    expect(formatAddressList(['a@x.com', '', 'b@y.com'])).toBe('a@x.com, b@y.com');
  });
});
