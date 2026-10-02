import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { ApplyLinkCard } from './ApplyLinkCard';
import { renderWithProviders } from '../test/utils';
import { server } from '../test/mocks/server';
import { BASE } from '../test/mocks/handlers';
import { applyLinkActive } from '../test/mocks/fixtures';

const LINK_URL = applyLinkActive.url;

function renderCard() {
  return renderWithProviders(<ApplyLinkCard jdId="jd-1" />);
}

describe('ApplyLinkCard', () => {
  it('generates a link when none exists yet', async () => {
    server.use(
      http.get(`${BASE}/api/jds/jd-1/apply-link`, () =>
        HttpResponse.json({ exists: false, enabled: false, url: null }),
      ),
      http.post(`${BASE}/api/jds/jd-1/apply-link`, () => HttpResponse.json(applyLinkActive)),
    );

    renderCard();

    fireEvent.click(await screen.findByRole('button', { name: /Generate application link/i }));
    expect(await screen.findByDisplayValue(LINK_URL)).toBeInTheDocument();
  });

  it('copies the link to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    server.use(
      http.get(`${BASE}/api/jds/jd-1/apply-link`, () => HttpResponse.json(applyLinkActive)),
    );

    renderCard();

    fireEvent.click(await screen.findByRole('button', { name: /Copy link/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(LINK_URL));
  });

  it('toggles the link active/inactive', async () => {
    let putBody: unknown = null;
    server.use(
      http.get(`${BASE}/api/jds/jd-1/apply-link`, () => HttpResponse.json(applyLinkActive)),
      http.put(`${BASE}/api/jds/jd-1/apply-link`, async ({ request }) => {
        putBody = await request.json();
        return HttpResponse.json({ ...applyLinkActive, enabled: false });
      }),
    );

    renderCard();

    const toggle = await screen.findByRole('checkbox');
    expect(toggle).toBeChecked();
    fireEvent.click(toggle);

    await waitFor(() => expect(putBody).toEqual({ enabled: false }));
  });

  it('regenerates the link after confirmation', async () => {
    server.use(
      http.get(`${BASE}/api/jds/jd-1/apply-link`, () => HttpResponse.json(applyLinkActive)),
      http.post(`${BASE}/api/jds/jd-1/apply-link`, () =>
        HttpResponse.json({ ...applyLinkActive, url: 'http://localhost:5173/apply/new-token-999' }),
      ),
    );

    renderCard();

    // Open the confirm dialog from the card's Regenerate button.
    fireEvent.click(await screen.findByRole('button', { name: /Regenerate/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/current link will stop working/i)).toBeInTheDocument();

    // Confirm.
    fireEvent.click(within(dialog).getByRole('button', { name: /Regenerate/i }));
    expect(await screen.findByDisplayValue(/new-token-999/)).toBeInTheDocument();
  });
});
