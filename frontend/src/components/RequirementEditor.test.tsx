import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RequirementEditor } from './RequirementEditor';
import type { RequirementInput } from '../api/types';
import { emptyRequirement } from '../lib/requirements';
import { renderWithProviders } from '../test/utils';

function Harness() {
  const [rows, setRows] = useState<RequirementInput[]>([emptyRequirement()]);
  return (
    <>
      <RequirementEditor value={rows} onChange={setRows} />
      <div data-testid="count">{rows.length}</div>
    </>
  );
}

describe('RequirementEditor', () => {
  it('starts with one row whose remove button is disabled (min 1)', () => {
    renderWithProviders(<Harness />, { withRouter: false });
    expect(screen.getByTestId('count')).toHaveTextContent('1');
    expect(screen.getByRole('button', { name: /remove requirement/i })).toBeDisabled();
  });

  it('adds a requirement row', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness />, { withRouter: false });
    await user.click(screen.getByRole('button', { name: /add requirement/i }));
    expect(screen.getByTestId('count')).toHaveTextContent('2');
  });

  it('removes a row once more than one exists', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness />, { withRouter: false });
    await user.click(screen.getByRole('button', { name: /add requirement/i }));
    const removeButtons = screen.getAllByRole('button', { name: /remove requirement/i });
    expect(removeButtons[0]).toBeEnabled();
    await user.click(removeButtons[0]);
    expect(screen.getByTestId('count')).toHaveTextContent('1');
  });

  it('edits the requirement text', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness />, { withRouter: false });
    const input = screen.getByRole('textbox', { name: /^requirement$/i });
    await user.type(input, 'React');
    expect(input).toHaveValue('React');
  });
});
