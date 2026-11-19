/**
 * Group editor: the finer printer permissions sit under Control Printers and
 * show as ticked and locked while the umbrella is on (#3248).
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { GroupEditPage } from '../../pages/GroupEditPage';
import { server } from '../mocks/server';

const mockPermissions = {
  categories: [
    {
      name: 'Printers',
      permissions: [
        { value: 'printers:read', label: 'Read Printers' },
        { value: 'printers:control', label: 'Control Printers' },
        { value: 'printers:pause_resume', label: 'Pause and resume' },
        { value: 'printers:stop', label: 'Stop print' },
      ],
    },
  ],
  all_permissions: ['printers:read', 'printers:control', 'printers:pause_resume', 'printers:stop'],
};

const mockPermissionsTwoCategories = {
  categories: [
    ...mockPermissions.categories,
    { name: 'Queue', permissions: [{ value: 'queue:read', label: 'Read Queue' }] },
  ],
  all_permissions: [...mockPermissions.all_permissions, 'queue:read'],
};

let posted: { permissions?: string[] } | null = null;

const box = (label: string) => screen.getByText(label).closest('label')!.querySelector('input')!;

describe('GroupEditPage printer permissions (#3248)', () => {
  beforeEach(() => {
    posted = null;
    server.use(
      http.get('/api/v1/groups/permissions', () => HttpResponse.json(mockPermissions)),
      http.post('/api/v1/groups/', async ({ request }) => {
        posted = (await request.json()) as { permissions?: string[] };
        return HttpResponse.json({
          id: 10, ...posted, is_system: false, user_count: 0,
          created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
        });
      }),
    );
  });

  it('indents the fine permissions under Control Printers', async () => {
    render(<GroupEditPage />);
    await waitFor(() => expect(screen.getByText('Pause and resume')).toBeInTheDocument());
    expect(screen.getByText('Pause and resume').closest('label')).toHaveClass('ml-7');
    expect(screen.getByText('Stop print').closest('label')).toHaveClass('ml-7');
    expect(screen.getByText('Control Printers').closest('label')).not.toHaveClass('ml-7');
  });

  it('a fine permission can be ticked on its own', async () => {
    const user = userEvent.setup();
    render(<GroupEditPage />);
    await waitFor(() => expect(screen.getByText('Pause and resume')).toBeInTheDocument());

    await user.click(box('Pause and resume'));
    expect(box('Pause and resume')).toBeChecked();
    expect(box('Pause and resume')).toBeEnabled();
    expect(box('Stop print')).not.toBeChecked();
    expect(box('Control Printers')).not.toBeChecked();
  });

  it('ticking Control Printers shows the fine permissions checked and locked', async () => {
    const user = userEvent.setup();
    render(<GroupEditPage />);
    await waitFor(() => expect(screen.getByText('Control Printers')).toBeInTheDocument());

    await user.click(box('Control Printers'));
    for (const label of ['Pause and resume', 'Stop print']) {
      expect(box(label)).toBeChecked();
      expect(box(label)).toBeDisabled();
    }

    await user.click(box('Control Printers'));
    expect(box('Stop print')).not.toBeChecked();
    expect(box('Stop print')).toBeEnabled();
  });

  it('saves only what was ticked, the umbrella alone does not add rows', async () => {
    const user = userEvent.setup();
    render(<GroupEditPage />);
    await waitFor(() => expect(screen.getByText('Control Printers')).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText(/group name/i), 'Farm');
    await user.click(box('Control Printers'));
    await user.click(screen.getByText('Save'));
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.permissions).toEqual(['printers:control']);
  });

  describe('with Control Printers already ticked', () => {
    const useTwoCategories = () =>
      server.use(http.get('/api/v1/groups/permissions', () => HttpResponse.json(mockPermissionsTwoCategories)));

    const saveName = async (user: ReturnType<typeof userEvent.setup>) => {
      await user.type(screen.getByPlaceholderText(/group name/i), 'Farm');
      await user.click(screen.getByText('Save'));
      await waitFor(() => expect(posted).not.toBeNull());
    };

    it('category select-all does not add rows the umbrella implies', async () => {
      useTwoCategories();
      const user = userEvent.setup();
      render(<GroupEditPage />);
      await waitFor(() => expect(screen.getByText('Control Printers')).toBeInTheDocument());

      await user.click(box('Control Printers'));
      // The Printers header checkbox is now partial (Read Printers missing): ticking completes it.
      await user.click(screen.getByText('Printers').parentElement!.querySelector('button')!);
      await saveName(user);
      expect([...posted!.permissions!].sort()).toEqual(['printers:control', 'printers:read']);
    });

    it('global select-all does not add implied rows, and the counter counts them', async () => {
      useTwoCategories();
      const user = userEvent.setup();
      render(<GroupEditPage />);
      await waitFor(() => expect(screen.getByText('Control Printers')).toBeInTheDocument());

      await user.click(box('Control Printers'));
      // Control + its two children + nothing else yet = 3 of 5
      expect(screen.getByText('3 selected / 5')).toBeInTheDocument();

      await user.click(screen.getByText('Select All'));
      expect(screen.getByText('5 selected / 5')).toBeInTheDocument();
      await saveName(user);
      expect([...posted!.permissions!].sort()).toEqual(['printers:control', 'printers:read', 'queue:read']);
    });
  });

  it('implied rows explain themselves and have no hover highlight', async () => {
    const user = userEvent.setup();
    render(<GroupEditPage />);
    await waitFor(() => expect(screen.getByText('Control Printers')).toBeInTheDocument());

    expect(screen.getByText('Stop print').closest('label')).not.toHaveAttribute('title');
    expect(screen.getByText('Stop print').closest('label')).toHaveClass('hover:bg-bambu-dark-secondary');
    await user.click(box('Control Printers'));
    const label = screen.getByText('Stop print').closest('label')!;
    expect(label).toHaveAttribute('title', 'Included in Control Printers');
    expect(label).not.toHaveClass('hover:bg-bambu-dark-secondary');
  });

  it('search matches the category name and keeps its rows', async () => {
    const user = userEvent.setup();
    render(<GroupEditPage />);
    await waitFor(() => expect(screen.getByText('Control Printers')).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText(/search permissions/i), 'printers');
    expect(screen.getByText('Read Printers')).toBeInTheDocument();
    expect(screen.getByText('Stop print')).toBeInTheDocument();
  });

  it('drops the indent when the Control Printers row is filtered out', async () => {
    const user = userEvent.setup();
    render(<GroupEditPage />);
    await waitFor(() => expect(screen.getByText('Stop print')).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText(/search permissions/i), 'stop');
    expect(screen.queryByText('Control Printers')).toBeNull();
    expect(screen.getByText('Stop print').closest('label')).not.toHaveClass('ml-7');
  });
});
