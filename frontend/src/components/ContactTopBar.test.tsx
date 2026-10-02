import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { ContactTopBar, type ContactCandidate } from './ContactTopBar';
import { renderWithProviders } from '../test/utils';

const SUBJECT = 'Role — next steps';

function setup(selected: ContactCandidate[], overrides: Partial<Parameters<typeof ContactTopBar>[0]> = {}) {
  const onTopNChange = vi.fn();
  const onRemove = vi.fn();
  renderWithProviders(
    <ContactTopBar
      selected={selected}
      topN={selected.length}
      maxN={selected.length}
      isCustom={false}
      onTopNChange={onTopNChange}
      onRemove={onRemove}
      subject={SUBJECT}
      {...overrides}
    />,
    { withRouter: false },
  );
  return { onTopNChange, onRemove };
}

describe('ContactTopBar', () => {
  it('counts selected vs with-email and flags those without an email', () => {
    setup([
      { cvId: '1', name: 'Ana', email: 'ana@x.com' },
      { cvId: '2', name: 'Bob', email: null },
    ]);
    expect(screen.getByText('2 selected · 1 with email')).toBeInTheDocument();
    expect(screen.getByText('1 without email')).toBeInTheDocument();
  });

  it('builds a BCC mailto that excludes candidates without an email', () => {
    setup([
      { cvId: '1', name: 'Ana', email: 'ana@x.com' },
      { cvId: '2', name: 'Bob', email: null },
    ]);
    const link = screen.getByRole('link', { name: /Open in email/i });
    const href = link.getAttribute('href') ?? '';
    expect(href).toContain('bcc=ana%40x.com');
    expect(href).not.toContain('Bob');
    expect(href).toContain('subject=');
  });

  it('copies only the addresses with an email', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    setup([
      { cvId: '1', name: 'Ana', email: 'ana@x.com' },
      { cvId: '2', name: 'Bob', email: null },
      { cvId: '3', name: 'Cara', email: 'cara@x.com' },
    ]);
    fireEvent.click(screen.getByRole('button', { name: /Copy addresses/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('ana@x.com, cara@x.com'));
  });

  it('disables email/copy when nobody selected has an email', () => {
    setup([{ cvId: '2', name: 'Bob', email: null }]);
    expect(screen.getByRole('button', { name: /Copy addresses/i })).toBeDisabled();
    // With no recipients the action degrades to a disabled button (no link).
    expect(screen.queryByRole('link', { name: /Open in email/i })).not.toBeInTheDocument();
  });

  it('falls back to copy when the mailto would exceed the URL limit', () => {
    const many: ContactCandidate[] = Array.from({ length: 80 }, (_, i) => ({
      cvId: String(i),
      name: `Person ${i}`,
      email: `person.with.a.fairly.long.address.${i}@example-company-domain.com`,
    }));
    setup(many);
    expect(screen.getByRole('button', { name: /Copy addresses/i })).toBeEnabled();
    expect(screen.queryByRole('link', { name: /Open in email/i })).not.toBeInTheDocument();
    expect(screen.getAllByText(/Too many addresses for a mailto link/i).length).toBeGreaterThan(0);
  });

  it('decrements the selection via the stepper', () => {
    const { onTopNChange } = setup([
      { cvId: '1', name: 'Ana', email: 'ana@x.com' },
      { cvId: '2', name: 'Bob', email: 'bob@x.com' },
    ]);
    fireEvent.click(screen.getByRole('button', { name: /Decrease selection/i }));
    expect(onTopNChange).toHaveBeenCalledWith(1);
  });
});
