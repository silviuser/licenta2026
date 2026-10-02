import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { DashboardPage } from './DashboardPage';
import { renderWithProviders } from '../test/utils';
import { server } from '../test/mocks/server';
import { BASE } from '../test/mocks/handlers';
import { emptyDashboard } from '../test/mocks/fixtures';

/** The KPI value lives in the same CardContent as its label. */
function kpiCard(label: string): HTMLElement {
  return screen.getByText(label).parentElement as HTMLElement;
}

describe('DashboardPage', () => {
  it('renders KPIs and the positions list from the API', async () => {
    renderWithProviders(<DashboardPage />);

    // KPI values scoped to their cards (the same numbers also appear in the table).
    expect(await screen.findByText('Open positions')).toBeInTheDocument();
    expect(within(kpiCard('Open positions')).getByText('2')).toBeInTheDocument();
    expect(within(kpiCard('Candidates (unique)')).getByText('3')).toBeInTheDocument();
    expect(within(kpiCard('CVs processing')).getByText('1')).toBeInTheDocument();

    // Last match KPI surfaces the JD title.
    expect(screen.getAllByText('Backend Engineer').length).toBeGreaterThan(0);

    // Positions table.
    expect(screen.getByText('Data Engineer')).toBeInTheDocument();
    // Backend Engineer's last match score is shown (78%).
    expect(screen.getAllByText('78%').length).toBeGreaterThan(0);
  });

  it('shows the empty state when there are no positions', async () => {
    server.use(http.get(`${BASE}/api/dashboard`, () => HttpResponse.json(emptyDashboard)));

    renderWithProviders(<DashboardPage />);

    expect(await screen.findByText('No positions yet.')).toBeInTheDocument();
  });
});
