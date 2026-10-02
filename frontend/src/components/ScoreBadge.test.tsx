import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { ScoreBadge } from './ScoreBadge';
import { scoreBand } from '../lib/scoreBand';
import { renderWithProviders } from '../test/utils';

describe('ScoreBadge', () => {
  it('renders the rounded percentage and the band label', () => {
    renderWithProviders(<ScoreBadge score={0.78} />, { withRouter: false });
    expect(screen.getByText('78%')).toBeInTheDocument();
    expect(screen.getByText('Excellent')).toBeInTheDocument();
  });

  it('exposes an accessible label (not colour-only)', () => {
    renderWithProviders(<ScoreBadge score={0.42} />, { withRouter: false });
    expect(
      screen.getByLabelText('Match score 42 percent, Weak'),
    ).toBeInTheDocument();
  });

  it('labels a low score as Unsuitable', () => {
    renderWithProviders(<ScoreBadge score={0.1} />, { withRouter: false });
    expect(screen.getByText('Unsuitable')).toBeInTheDocument();
  });
});

describe('scoreBand cutoffs', () => {
  it.each([
    [85, 'Excellent'],
    [70, 'Excellent'],
    [69, 'Strong'],
    [60, 'Strong'],
    [59, 'Partial'],
    [50, 'Partial'],
    [49, 'Weak'],
    [30, 'Weak'],
    [29, 'Unsuitable'],
    [0, 'Unsuitable'],
  ])('maps %i%% to the %s band', (percent, label) => {
    expect(scoreBand(percent).label).toBe(label);
  });
});
