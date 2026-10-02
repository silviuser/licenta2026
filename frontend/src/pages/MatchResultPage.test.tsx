import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router-dom';
import type { CandidateReport, MatchJobResponse } from '../api/types';
import { MatchResultPage } from './MatchResultPage';
import * as cvsApi from '../api/cvs';
import { renderWithProviders } from '../test/utils';
import { server } from '../test/mocks/server';
import { BASE } from '../test/mocks/handlers';
import { runningJob, succeededJob } from '../test/mocks/fixtures';

/** A scored candidate, ranked #i with a descending score. */
function candidate(i: number): CandidateReport {
  return {
    rank: i,
    cv_id: `cv-${i}`,
    filename: `cv${i}.pdf`,
    source: 'DIRECT',
    source_jd_id: null,
    source_jd_title: null,
    origin: 'RECRUITER',
    candidate_name: null,
    candidate_email: null,
    candidate_phone: null,
    effective_email: `cand${i}@example.com`,
    email_source: 'EXTRACTED',
    status: 'SUCCEEDED',
    overall_score: 1 - i * 0.05,
    overall_class: 'possible',
    required_coverage: 0.5,
    nice_to_have_coverage: 0.5,
    matched_skills: [],
    missing_skills: { required: [], nice_to_have: [] },
    explanation: `Candidate ${i}.`,
    error_code: null,
  };
}

function jobWithCandidates(jobId: string, n: number): MatchJobResponse {
  const base = succeededJob(jobId);
  return {
    ...base,
    result: {
      jd_id: 'jd-1',
      source_jd_ids: [],
      generated_at: '2026-06-06T12:00:05Z',
      required_total: 2,
      nice_to_have_total: 2,
      candidates: Array.from({ length: n }, (_, idx) => candidate(idx + 1)),
    },
  };
}

describe('MatchResultPage polling (per-JD report)', () => {
  it('shows the analyzing state, then renders the ranked candidate report', async () => {
    // First poll → RUNNING, subsequent polls → SUCCEEDED.
    let calls = 0;
    server.use(
      http.get(`${BASE}/api/matches/:jobId`, ({ params }) => {
        calls += 1;
        const jobId = String(params.jobId);
        return HttpResponse.json(calls === 1 ? runningJob(jobId) : succeededJob(jobId));
      }),
    );

    renderWithProviders(
      <Routes>
        <Route path="/match/:jobId" element={<MatchResultPage />} />
      </Routes>,
      { initialEntries: ['/match/job-123'] },
    );

    // While RUNNING: the reassuring async copy is shown.
    expect(
      await screen.findByText(/Analyzing the CV and scoring it against the job/i),
    ).toBeInTheDocument();

    // After the poll lands SUCCEEDED: the candidate, score and explanation appear.
    await waitFor(
      () => {
        expect(screen.getByText('alice.pdf')).toBeInTheDocument();
      },
      { timeout: 6000 },
    );
    expect(screen.getByText('78%')).toBeInTheDocument();
    expect(screen.getByText('Strong match')).toBeInTheDocument();
    expect(screen.getByText(/Covers 1\/1 required/)).toBeInTheDocument();
    // Missing nice-to-have requirement is surfaced.
    expect(screen.getByText('Docker')).toBeInTheDocument();
  }, 10000);
});

describe('MatchResultPage — view CV', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    // Remove the object-URL helpers jsdom doesn't provide natively.
    delete (URL as unknown as Record<string, unknown>).createObjectURL;
    delete (URL as unknown as Record<string, unknown>).revokeObjectURL;
  });

  it('fetches the candidate CV via the authenticated file endpoint on click', async () => {
    const blob = new Blob(['%PDF'], { type: 'application/pdf' });
    const fetchSpy = vi.spyOn(cvsApi, 'fetchCvBlob').mockResolvedValue(blob);
    vi.stubGlobal(
      'open',
      vi.fn(() => ({ closed: false, location: { href: '' }, close: vi.fn() })),
    );
    // Add object-URL helpers onto the real URL (jsdom lacks them) without
    // replacing the URL constructor that the router/MSW rely on.
    (URL as unknown as Record<string, unknown>).createObjectURL = vi.fn(() => 'blob:mock');
    (URL as unknown as Record<string, unknown>).revokeObjectURL = vi.fn();

    renderWithProviders(
      <Routes>
        <Route path="/match/:jobId" element={<MatchResultPage />} />
      </Routes>,
      { initialEntries: ['/match/job-1'] },
    );

    fireEvent.click(await screen.findByRole('button', { name: /View CV for alice\.pdf/i }));
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith('cv-1'));
    expect(window.open).toHaveBeenCalled();
  });
});

describe('MatchResultPage top-N ranking', () => {
  it('shows only the top 5 by default and reveals the rest on demand', async () => {
    server.use(
      http.get(`${BASE}/api/matches/:jobId`, ({ params }) =>
        HttpResponse.json(jobWithCandidates(String(params.jobId), 7)),
      ),
    );

    renderWithProviders(
      <Routes>
        <Route path="/match/:jobId" element={<MatchResultPage />} />
      </Routes>,
      { initialEntries: ['/match/job-top'] },
    );

    // Top 5 visible; #6 and #7 hidden behind the toggle.
    expect(await screen.findByText('cv1.pdf')).toBeInTheDocument();
    expect(screen.getByText('cv5.pdf')).toBeInTheDocument();
    expect(screen.queryByText('cv6.pdf')).not.toBeInTheDocument();
    expect(screen.queryByText('cv7.pdf')).not.toBeInTheDocument();
    expect(screen.getByText('Showing the top 5 of 7 candidates.')).toBeInTheDocument();

    // Expand → all 7 visible.
    fireEvent.click(screen.getByRole('button', { name: /Show all 7 candidates/i }));
    expect(await screen.findByText('cv7.pdf')).toBeInTheDocument();
    expect(screen.getByText('cv6.pdf')).toBeInTheDocument();

    // Collapse back → top 5 only.
    fireEvent.click(screen.getByRole('button', { name: /Show top 5/i }));
    await waitFor(() => expect(screen.queryByText('cv7.pdf')).not.toBeInTheDocument());
    expect(screen.getByText('cv5.pdf')).toBeInTheDocument();
  });
});
