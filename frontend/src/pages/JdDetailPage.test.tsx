import { describe, expect, it } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router-dom';
import { JdDetailPage } from './JdDetailPage';
import { renderWithProviders } from '../test/utils';
import { server } from '../test/mocks/server';
import { BASE } from '../test/mocks/handlers';
import { applicationViaLink } from '../test/mocks/fixtures';

function renderPage(initialEntry = '/jds/jd-1') {
  return renderWithProviders(
    <Routes>
      <Route path="/jds/:id" element={<JdDetailPage />} />
    </Routes>,
    { initialEntries: [initialEntry] },
  );
}

describe('JdDetailPage', () => {
  it('renders the position with requirements (source badges) and applications', async () => {
    renderPage();

    // Title + description.
    expect(await screen.findByText('Backend Engineer')).toBeInTheDocument();
    expect(screen.getByText(/Build and maintain backend services/)).toBeInTheDocument();

    // Requirements with provenance badges.
    expect(screen.getByText('Java')).toBeInTheDocument();
    expect(screen.getByText('extracted')).toBeInTheDocument();
    expect(screen.getByText('Docker')).toBeInTheDocument();
    expect(screen.getByText('manual')).toBeInTheDocument();

    // Applications list + run-match control.
    expect(await screen.findByText('alice.pdf')).toBeInTheDocument();
    expect(screen.getByText('Run a match')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Run match/i })).toBeInTheDocument();
  });

  it('shows the candidate-link origin badge and contact details (D37)', async () => {
    server.use(
      http.get(`${BASE}/api/jds/:id/applications`, () => HttpResponse.json([applicationViaLink])),
    );

    renderPage();

    expect(await screen.findByText('Bob Candidate')).toBeInTheDocument();
    expect(screen.getByText('Applied via link')).toBeInTheDocument();
    expect(screen.getByText(/bob@candidate\.com/)).toBeInTheDocument();
  });

  it('builds sourceJdIds from the selected source positions (D27)', async () => {
    let captured: unknown = null;
    server.use(
      http.post(`${BASE}/api/jds/jd-1/match`, async ({ request }) => {
        captured = await request.json();
        return HttpResponse.json({ jobId: 'job-9', status: 'PENDING' });
      }),
    );

    renderPage();

    // Open the match dialog.
    fireEvent.click(await screen.findByRole('button', { name: 'Run match' }));
    const dialog = await screen.findByRole('dialog');

    // Enable selective pooling, then pick the only other position (Data Engineer).
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /pull in candidates/i }));
    fireEvent.click(await within(dialog).findByText('Data Engineer'));

    fireEvent.click(within(dialog).getByRole('button', { name: 'Run match' }));

    await waitFor(() => expect(captured).toEqual({ sourceJdIds: ['jd-2'] }));
  });

  it('sends an empty sourceJdIds list when pooling is on but nothing is selected', async () => {
    let captured: unknown = null;
    server.use(
      http.post(`${BASE}/api/jds/jd-1/match`, async ({ request }) => {
        captured = await request.json();
        return HttpResponse.json({ jobId: 'job-9', status: 'PENDING' });
      }),
    );

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Run match' }));
    const dialog = await screen.findByRole('dialog');

    // Toggle pooling on but select nothing.
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /pull in candidates/i }));
    // Ensure the source list has loaded before launching.
    await within(dialog).findByText('Data Engineer');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Run match' }));

    await waitFor(() => expect(captured).toEqual({ sourceJdIds: [] }));
  });
});
