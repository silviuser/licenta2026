import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import type { CvResponse } from '../api/types';
import { CandidateEmailCell } from './CandidateEmailCell';
import * as cvsApi from '../api/cvs';
import { renderWithProviders } from '../test/utils';

const SUBJECT = 'Role — next steps';

const updatedCv: CvResponse = {
  id: 'cv-1',
  originalFilename: 'alice.pdf',
  contentType: 'application/pdf',
  sizeBytes: 1,
  detectedLanguage: 'en',
  extractionCached: true,
  processingStatus: 'READY',
  processingError: null,
  contentHash: 'h',
  extractedEmail: 'ana@x.com',
  manualEmail: 'edited@x.com',
  effectiveEmail: 'edited@x.com',
  emailSource: 'MANUAL',
  createdAt: '2026-06-06T12:00:00Z',
};

afterEach(() => vi.restoreAllMocks());

describe('CandidateEmailCell', () => {
  it('shows the resolved email, its source badge and a mailto with the subject', () => {
    renderWithProviders(
      <CandidateEmailCell cvId="cv-1" email="ana@x.com" source="EXTRACTED" subject={SUBJECT} />,
      { withRouter: false },
    );
    expect(screen.getByText('ana@x.com')).toBeInTheDocument();
    expect(screen.getByText('from CV')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /Email ana@x.com/i });
    const href = link.getAttribute('href') ?? '';
    expect(href).toContain('mailto:ana%40x.com');
    expect(href).toContain('subject=Role%20%E2%80%94%20next%20steps');
  });

  it('disables the email action and badges "no email" when there is no address', () => {
    renderWithProviders(
      <CandidateEmailCell cvId="cv-1" email={null} source="NONE" subject={SUBJECT} />,
      { withRouter: false },
    );
    expect(screen.getByText('No email')).toBeInTheDocument();
    expect(screen.getByText('no email')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Email$/i })).toBeDisabled();
  });

  it('saves a manual email and reports the updated CV', async () => {
    const spy = vi.spyOn(cvsApi, 'updateCvEmail').mockResolvedValue(updatedCv);
    const onUpdated = vi.fn();
    renderWithProviders(
      <CandidateEmailCell
        cvId="cv-1"
        email="ana@x.com"
        source="EXTRACTED"
        subject={SUBJECT}
        onUpdated={onUpdated}
      />,
      { withRouter: false },
    );

    fireEvent.click(screen.getByRole('button', { name: /Edit email/i }));
    fireEvent.change(screen.getByLabelText(/Email address/i), {
      target: { value: 'edited@x.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    await waitFor(() => expect(spy).toHaveBeenCalledWith('cv-1', 'edited@x.com'));
    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(updatedCv));
  });

  it('rejects an invalid address client-side (save disabled)', () => {
    const spy = vi.spyOn(cvsApi, 'updateCvEmail');
    renderWithProviders(
      <CandidateEmailCell cvId="cv-1" email="ana@x.com" source="EXTRACTED" subject={SUBJECT} />,
      { withRouter: false },
    );
    fireEvent.click(screen.getByRole('button', { name: /Edit email/i }));
    fireEvent.change(screen.getByLabelText(/Email address/i), { target: { value: 'not-an-email' } });
    expect(screen.getByText(/Enter a valid email address/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Save$/i })).toBeDisabled();
    expect(spy).not.toHaveBeenCalled();
  });

  it('clearing the field sends null to revert to the extracted address', async () => {
    const spy = vi.spyOn(cvsApi, 'updateCvEmail').mockResolvedValue(updatedCv);
    renderWithProviders(
      <CandidateEmailCell cvId="cv-1" email="edited@x.com" source="MANUAL" subject={SUBJECT} />,
      { withRouter: false },
    );
    fireEvent.click(screen.getByRole('button', { name: /Edit email/i }));
    // Field pre-fills the current manual address; clear it.
    fireEvent.change(screen.getByLabelText(/Email address/i), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith('cv-1', null));
  });
});
