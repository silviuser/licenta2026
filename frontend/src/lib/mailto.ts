/**
 * mailto: URL builders (REWORK 4 D44/D47).
 *
 * Everything is `encodeURIComponent`-sanitised. Multi-candidate actions use
 * `bcc` so candidate addresses are never exposed to each other (D47). A pure
 * module so the URL/length logic is unit-testable without a DOM.
 */
import { MAILTO_MAX_URL } from './constants';

export interface MailtoOptions {
  to?: string;
  bcc?: string[];
  subject?: string;
}

/** Build a sanitised `mailto:` URL. Empty recipient lists are omitted. */
export function buildMailto({ to, bcc, subject }: MailtoOptions): string {
  const params: string[] = [];
  const bccList = (bcc ?? []).filter(Boolean);
  if (bccList.length > 0) {
    params.push(`bcc=${encodeURIComponent(bccList.join(','))}`);
  }
  if (subject) {
    params.push(`subject=${encodeURIComponent(subject)}`);
  }
  const query = params.length > 0 ? `?${params.join('&')}` : '';
  return `mailto:${encodeURIComponent(to ?? '')}${query}`;
}

/** True when the built URL is short enough to be practical across mail clients (D47). */
export function isMailtoWithinLimit(url: string): boolean {
  return url.length <= MAILTO_MAX_URL;
}

/** Format addresses for the clipboard: `a@b.com, c@d.com`. */
export function formatAddressList(emails: string[]): string {
  return emails.filter(Boolean).join(', ');
}
