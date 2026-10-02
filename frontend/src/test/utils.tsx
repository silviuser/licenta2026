import type { ReactElement, ReactNode } from 'react';
import { render } from '@testing-library/react';
import type { RenderOptions } from '@testing-library/react';
import { ThemeProvider } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '../components/ToastProvider';
import { theme } from '../theme/theme';

interface Options extends Omit<RenderOptions, 'wrapper'> {
  initialEntries?: string[];
  /** Set false to render without a router (e.g. presentational components). */
  withRouter?: boolean;
}

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

export function renderWithProviders(ui: ReactElement, options: Options = {}) {
  const { initialEntries = ['/'], withRouter = true, ...rest } = options;
  const queryClient = makeQueryClient();

  function Wrapper({ children }: { children: ReactNode }) {
    const inner = (
      <ThemeProvider theme={theme}>
        <QueryClientProvider client={queryClient}>
          <ToastProvider>{children}</ToastProvider>
        </QueryClientProvider>
      </ThemeProvider>
    );
    return withRouter ? (
      <MemoryRouter
        initialEntries={initialEntries}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        {inner}
      </MemoryRouter>
    ) : (
      inner
    );
  }

  return { queryClient, ...render(ui, { wrapper: Wrapper, ...rest }) };
}
