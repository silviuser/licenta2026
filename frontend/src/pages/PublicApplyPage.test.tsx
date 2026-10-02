import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { Route, Routes } from 'react-router-dom';
import { PublicApplyPage } from './PublicApplyPage';
import * as publicApi from '../api/public';
import { renderWithProviders } from '../test/utils';
import { server } from '../test/mocks/server';
import { BASE } from '../test/mocks/handlers';

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPage(token = 'tok') {
  return renderWithProviders(
    <Routes>
      <Route path="/apply/:token" element={<PublicApplyPage />} />
    </Routes>,
    { initialEntries: [`/apply/${token}`] },
  );
}

describe('PublicApplyPage', () => {
  it('renders the job title and description from the API', async () => {
    server.use(
      http.get(`${BASE}/api/public/apply/tok`, () =>
        HttpResponse.json({ jobTitle: 'Backend Engineer', jobDescription: 'Build backend services.' }),
      ),
    );

    renderPage();

    expect(await screen.findByText('Backend Engineer')).toBeInTheDocument();
    expect(screen.getByText('Build backend services.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Submit application/i })).toBeInTheDocument();
  });

  it('shows an unavailable message for a disabled/invalid link (404)', async () => {
    server.use(
      http.get(`${BASE}/api/public/apply/bad`, () =>
        HttpResponse.json({ error: 'not_found', detail: 'not found' }, { status: 404 }),
      ),
    );

    renderPage('bad');

    expect(await screen.findByText(/no longer available/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Submit application/i })).not.toBeInTheDocument();
  });

  it('submits an application and shows the confirmation screen', async () => {
    // Spy at the API boundary: a real multipart POST is covered by the backend
    // PublicApplyFlowIT; here we only assert the page's submit → confirmation flow
    // (avoids jsdom quirks serialising a File through XHR).
    const submitSpy = vi
      .spyOn(publicApi, 'submitApplication')
      .mockResolvedValue({ status: 'RECEIVED', message: 'ok' });
    server.use(
      http.get(`${BASE}/api/public/apply/tok`, () =>
        HttpResponse.json({ jobTitle: 'Role', jobDescription: null }),
      ),
    );

    const { container } = renderPage();
    await screen.findByText('Role');

    fireEvent.change(screen.getByLabelText(/Full name/i), { target: { value: 'Alice' } });
    fireEvent.change(screen.getByLabelText(/Email/i), { target: { value: 'alice@x.com' } });
    fireEvent.change(screen.getByLabelText(/Phone/i), { target: { value: '0712345678' } });

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['%PDF-1.7 content'], 'cv.pdf', { type: 'application/pdf' });
    fireEvent.change(fileInput, { target: { files: [file] } });
    expect(await screen.findByText('cv.pdf')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Submit application/i }));

    expect(await screen.findByText(/Your application has been received/i)).toBeInTheDocument();
    expect(submitSpy).toHaveBeenCalledWith(
      'tok',
      expect.objectContaining({ name: 'Alice', email: 'alice@x.com', phone: '0712345678', file }),
    );
  });

  it('blocks submission and shows inline errors when fields are invalid', async () => {
    server.use(
      http.get(`${BASE}/api/public/apply/tok`, () =>
        HttpResponse.json({ jobTitle: 'Role', jobDescription: null }),
      ),
    );

    renderPage();
    await screen.findByText('Role');

    // Submit with everything empty → inline validation, no confirmation.
    fireEvent.click(screen.getByRole('button', { name: /Submit application/i }));

    expect(await screen.findByText(/Please enter a valid email address/i)).toBeInTheDocument();
    expect(screen.getByText(/Please attach your résumé/i)).toBeInTheDocument();
    expect(screen.queryByText(/has been received/i)).not.toBeInTheDocument();
  });
});
