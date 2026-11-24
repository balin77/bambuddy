/**
 * A paused print is resumed or stopped from its To do entry (#3726): the printer
 * card's calls and stop question, each button by its permission and the hide
 * option (#3639).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent, render as rtlRender } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '../../contexts/ToastContext';
import type { PrintQueueItem, QueueTodo, QueueTodoEntry } from '../../api/client';

const perms = { granted: new Set<string>(), hide: false, ownerOk: (_owner: number | null | undefined) => true };

vi.mock('../../contexts/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../contexts/AuthContext')>();
  return {
    ...actual,
    useAuth: () => ({
      user: { id: 1, username: 'op', permissions: [] },
      authEnabled: true,
      loading: false,
      isAdmin: false,
      hasPermission: (p: string) => perms.granted.has(p),
      hideUnpermitted: perms.hide,
      hasAnyPermission: (...ps: string[]) => ps.some((p) => perms.granted.has(p)),
      canModify: (_r: string, _a: string, owner: number | null | undefined) =>
        (perms.granted.has('queue:update_all') || perms.granted.has('queue:update_own')) && perms.ownerOk(owner),
    }),
  };
});


import { api } from '../../api/client';
import { QueueTodoList } from '../../components/QueueTodoList';

const paused: QueueTodoEntry = {
  kind: 'print_paused',
  jobs: [],
  filaments: [],
  printers: [],
  detail: null,
  paused: { job_name: 'Benchy', progress: 40, remaining_minutes: 30, cause: 'paused', ran_out: null, expected: null, error: null, more_errors: 0 },
};
const todo: QueueTodo = {
  count: 1,
  groups: [{ printer_id: 3, printer_name: 'Shelf X1C', target_model: null, prepare: [], entries: [paused] }],
};

let client: QueryClient;
function renderList() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  rtlRender(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <QueueTodoList todo={todo} overlayZIndex="z-[70]" />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return invalidate;
}

beforeEach(() => {
  vi.restoreAllMocks();
  perms.granted = new Set(['printers:pause_resume', 'printers:stop']);
  perms.hide = false;
});

describe('Resume and Stop of a paused entry', () => {
  it('has both buttons, 44 px high on a phone, Resume filled and Stop outlined', () => {
    renderList();
    const resume = screen.getByRole('button', { name: 'Resume' });
    const stop = screen.getByRole('button', { name: 'Stop' });
    expect(resume.className).toContain('bg-bambu-green');
    expect(stop.className).toContain('border');
    expect(stop.className).not.toContain('bg-bambu-green');
    for (const b of [resume, stop]) expect(b.className).toContain('min-h-[44px]');
  });

  it('resumes the printer of the entry, says so and refreshes the list and the printer', async () => {
    const resume = vi.spyOn(api, 'resumePrint').mockResolvedValue({ success: true } as never);
    const invalidate = renderList();
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }));
    await waitFor(() => expect(resume).toHaveBeenCalledWith(3));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['printerStatus', 3] }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['queue-todo'] });
  });

  it('asks before it stops, and stops only on confirm', async () => {
    const stop = vi.spyOn(api, 'stopPrint').mockResolvedValue({ success: true } as never);
    const invalidate = renderList();
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
    expect(stop).not.toHaveBeenCalled();
    expect(document.querySelector('[data-todo-modal-open]')).not.toBeNull();
    const dialog = await screen.findByText(/Shelf X1C/, { selector: 'p' });
    expect(dialog).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Stop Print' }));
    await waitFor(() => expect(stop).toHaveBeenCalledWith(3));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['printerStatus', 3] }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['queue-todo'] });
  });

  it('does nothing when the question is cancelled', async () => {
    const stop = vi.spyOn(api, 'stopPrint').mockResolvedValue({ success: true } as never);
    renderList();
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    expect(stop).not.toHaveBeenCalled();
    expect(document.querySelector('[data-todo-modal-open]')).toBeNull();
  });

  it('greys a button out, with the reason, for who may not use it', () => {
    perms.granted = new Set(['printers:stop']);
    renderList();
    const resume = screen.getByRole('button', { name: 'Resume' });
    expect(resume).toBeDisabled();
    expect(resume).toHaveAttribute('title', 'You do not have permission to control printers');
    expect(screen.getByRole('button', { name: 'Stop' })).toBeEnabled();
    perms.granted = new Set();
  });

  it('greys both out without any permission', () => {
    perms.granted = new Set();
    renderList();
    expect(screen.getByRole('button', { name: 'Resume' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeDisabled();
  });

  it('leaves out what the caller may not use when the hide option is on', () => {
    perms.hide = true;
    perms.granted = new Set(['printers:pause_resume']);
    renderList();
    expect(screen.getByRole('button', { name: 'Resume' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Stop' })).toBeNull();
  });

  it('draws no row at all without both permissions and the hide option on', () => {
    perms.hide = true;
    perms.granted = new Set();
    renderList();
    expect(screen.queryByTestId('todo-paused-actions')).toBeNull();
    expect(screen.getByTestId('todo-entry-print_paused')).toBeInTheDocument();
  });
});
