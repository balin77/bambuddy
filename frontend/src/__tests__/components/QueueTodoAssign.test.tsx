/**
 * Assigning a spool inside a To do entry (#3726): the shared picker's inline
 * layout, the buttons of the entry and who sees them.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent, within, render as rtlRender } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { ToastProvider } from '../../contexts/ToastContext';
import { server } from '../mocks/server';
import type { QueueTodoPicture, QueueTodoPictureSlot } from '../../api/client';

const perms = { granted: new Set<string>(), hide: false };

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
      canModify: () => true,
    }),
  };
});

import { PictureActions } from '../../components/QueueTodoSlotActions';

const incoming = { filament_index: 0, type: 'PLA', color: '#C8102E', color_name: 'Lava Red', required_g: 505, stock_count: 3 };

function slot(trayId: number, overrides: Partial<QueueTodoPictureSlot> = {}): QueueTodoPictureSlot {
  return {
    ams_id: 0, tray_id: trayId, is_ht: false, is_external: false, ams_type: 1, type: 'PLA', color: '#C8102E',
    extra_colors: '', effect_type: '', subtype: '', color_name: '', tray_sub_brands: '', tray_info_idx: '',
    remaining_g: null, remain_percent: null, rfid: false, state: 'keep', incoming: null, ...overrides,
  };
}

const picture: QueueTodoPicture = {
  printer_id: 7,
  printer_name: 'Shelf P1S right',
  compact: false,
  unplaced: [],
  units: [{
    ams_id: 0, ams_type: 1, kind: 'ams', nozzle: null, collapsed: false,
    slots: [slot(0), slot(1), slot(2, { state: 'out', incoming }), slot(3, { type: '', color: '', state: 'empty' })],
  }],
};

function spool(id: number, extra: Record<string, unknown> = {}) {
  return {
    id, material: 'PLA', subtype: 'PolyTerra', brand: 'Polymaker', color_name: 'Lava Red', rgba: 'C8102EFF',
    label_weight: 1000, weight_used: 0, storage_location: 'Shelf B2', archived_at: null, slicer_filament_name: 'PLA', ...extra,
  };
}

const spools = [
  spool(152, { weight_used: 690 }),
  spool(187, { weight_used: 380 }),
  spool(214),
  spool(300, { rgba: '0000FFFF', color_name: 'Blue' }),
];

function setup(opts: { spoolman?: 'off' | 'on' | 'down'; spoolmanSpools?: unknown[] } = {}) {
  const sent: { path: string; body: unknown }[] = [];
  server.use(
    http.get('/api/v1/inventory/spools', () => HttpResponse.json(spools)),
    http.get('/api/v1/inventory/assignments', () => HttpResponse.json([])),
    http.get('/api/v1/settings/', () => HttpResponse.json({})),
    http.get('/api/v1/spoolman/status', () =>
      HttpResponse.json({ enabled: opts.spoolman !== undefined && opts.spoolman !== 'off', connected: opts.spoolman === 'on', url: 'http://sm' }),
    ),
    http.get('/api/v1/spoolman/inventory/spools', () => HttpResponse.json(opts.spoolmanSpools ?? [])),
    http.get('/api/v1/spoolman/inventory/slot-assignments', () => HttpResponse.json([])),
    http.post('/api/v1/inventory/assignments', async ({ request }) => {
      const body = await request.json();
      sent.push({ path: 'assign', body });
      return HttpResponse.json({ id: 1, ...(body as object), pending_config: false });
    }),
    http.post('/api/v1/spoolman/inventory/slot-assignments', async ({ request }) => {
      sent.push({ path: 'spoolman', body: await request.json() });
      return HttpResponse.json({ id: 9 });
    }),
    http.post('/api/v1/printers/7/refresh-status', () => HttpResponse.json({})),
  );
  return sent;
}

function renderActions(pic: QueueTodoPicture = picture) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const view = rtlRender(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <PictureActions picture={pic} />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { invalidate, ...view };
}

beforeEach(() => {
  perms.granted = new Set(['inventory:update', 'inventory:create', 'printers:filament']);
  perms.hide = false;
});

describe('buttons of an entry with a picture', () => {
  it('offers assigning to the slot the filament goes into, and setting up a slot without RFID', async () => {
    setup();
    renderActions();
    expect(await screen.findByRole('button', { name: 'Assign spool for A3' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Set up slot A3' })).toBeInTheDocument();
  });

  it('sets no slot up that has an RFID spool', async () => {
    setup();
    const rfid = { ...picture, units: [{ ...picture.units[0], slots: [slot(2, { rfid: true, incoming })] }] };
    const client = new QueryClient();
    rtlRender(
      <QueryClientProvider client={client}><MemoryRouter><ToastProvider><PictureActions picture={rfid} /></ToastProvider></MemoryRouter></QueryClientProvider>,
    );
    expect(await screen.findByRole('button', { name: 'Assign spool for A3' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Set up slot/ })).toBeNull();
  });

  it('has no button for who holds no permission and whose groups hide what they cannot use, and no row at all', () => {
    setup();
    perms.granted = new Set();
    perms.hide = true;
    const { container } = renderActions();
    expect(screen.queryByRole('button')).toBeNull();
    expect(container.querySelector('[data-testid="todo-slot-actions"]')).toBeNull();
  });

  it('greys the buttons out, with the reason, for who may not use them', async () => {
    setup();
    perms.granted = new Set();
    renderActions();
    const assign = await screen.findByRole('button', { name: 'Assign spool for A3' });
    expect(assign).toBeDisabled();
    expect(assign).toHaveAttribute('title', 'You do not have permission to assign spools');
    const configure = screen.getByRole('button', { name: 'Set up slot A3' });
    expect(configure).toBeDisabled();
    expect(configure).toHaveAttribute('title', 'You do not have permission to set up AMS slots');
    fireEvent.click(assign);
    expect(screen.queryByTestId('todo-assign-picker')).toBeNull();
  });

  it('assigns with inventory:update alone and sets up with printers:filament alone (hide option on)', async () => {
    setup();
    perms.hide = true;
    perms.granted = new Set(['inventory:update']);
    const { unmount } = renderActions();
    expect(await screen.findByRole('button', { name: 'Assign spool for A3' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /Set up slot/ })).toBeNull();
    unmount();
    perms.granted = new Set(['printers:filament']);
    renderActions();
    expect(screen.queryByRole('button', { name: /Assign spool/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'Set up slot A3' })).toBeEnabled();
  });

  it('does not take printers:control for the slot set-up: only printers:filament', async () => {
    setup();
    perms.granted = new Set(['printers:control']);
    renderActions();
    expect(await screen.findByRole('button', { name: 'Set up slot A3' })).toBeDisabled();
  });

  it('makes every button at least 44 px high on a phone', () => {
    setup();
    renderActions();
    for (const button of screen.getAllByRole('button')) expect(button.className).toContain('min-h-[44px]');
  });

  it('offers no assigning while Spoolman is down', async () => {
    setup({ spoolman: 'down' });
    renderActions();
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Assign spool for A3' })).toBeNull());
    expect(screen.getByRole('button', { name: 'Set up slot A3' })).toBeInTheDocument();
  });
});

describe('the spools of the inventory inside the entry', () => {
  async function open() {
    const sent = setup();
    const view = renderActions();
    fireEvent.click(await screen.findByRole('button', { name: 'Assign spool for A3' }));
    await screen.findByTestId('todo-assign-picker');
    await screen.findAllByTestId('todo-assign-spool');
    return { sent, ...view };
  }

  it('asks which spool goes into the slot and what the job needs', async () => {
    await open();
    expect(screen.getByRole('heading', { name: 'Which spool goes into A3?' })).toBeInTheDocument();
    expect(screen.getByText('PLA Lava Red from the inventory. The job needs 505 g.')).toBeInTheDocument();
  });

  it('lists spools that cover the job first, by grams left, the one that does not dimmed with the reason', async () => {
    await open();
    const rows = screen.getAllByTestId('todo-assign-spool');
    // The blue spool is another colour: not offered.
    expect(rows).toHaveLength(3);
    expect(rows.map((r) => r.dataset.enough)).toEqual(['true', 'true', 'false']);
    expect(rows[0]).toHaveTextContent('Polymaker PLA PolyTerra · 1,000 g');
    expect(rows[0]).toHaveTextContent('new · Shelf B2 · Spool #214');
    expect(rows[1]).toHaveTextContent('620 g');
    expect(rows[1]).toHaveTextContent('opened · Shelf B2 · Spool #187');
    expect(rows[2]).toHaveTextContent('310 g');
    expect(rows[2]).toHaveTextContent('not enough for this job · Shelf B2 · Spool #152');
    expect(rows[2].className).toContain('opacity-60');
  });

  it('assigns the spool to the slot of the entry in one tap, then updates the list', async () => {
    const { sent, invalidate } = await open();
    const row = screen.getAllByTestId('todo-assign-spool')[1];
    fireEvent.click(within(row).getByRole('button', { name: /Assign spool Polymaker PLA PolyTerra #187/ }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].body).toEqual({ spool_id: 187, printer_id: 7, ams_id: 0, tray_id: 2 });
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['queue-todo'] }));
    // The picker closes and the buttons are back.
    expect(await screen.findByRole('button', { name: 'Assign spool for A3' })).toBeInTheDocument();
  });

  it('shows every spool when asked, and Back returns to the buttons', async () => {
    await open();
    fireEvent.click(screen.getByLabelText('Show all spools'));
    expect(screen.getAllByTestId('todo-assign-spool')).toHaveLength(4);
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.queryByTestId('todo-assign-picker')).toBeNull();
  });

  it('offers scanning the label (same slot) and a new spool with inventory:create', async () => {
    await open();
    expect(screen.getByRole('button', { name: 'Scan label' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add new spool' })).toBeInTheDocument();
  });

  it('greys the new spool out without inventory:create but keeps scanning', async () => {
    perms.granted = new Set(['inventory:update']);
    setup();
    renderActions();
    fireEvent.click(await screen.findByRole('button', { name: 'Assign spool for A3' }));
    await screen.findByTestId('todo-assign-picker');
    const add = screen.getByRole('button', { name: 'Add new spool' });
    expect(add).toBeDisabled();
    expect(add).toHaveAttribute('title', 'You do not have permission to add spools');
    expect(screen.getByRole('button', { name: 'Scan label' })).toBeInTheDocument();
  });

  it('leaves the new spool out without inventory:create when the hide option is on', async () => {
    perms.granted = new Set(['inventory:update']);
    perms.hide = true;
    setup();
    renderActions();
    fireEvent.click(await screen.findByRole('button', { name: 'Assign spool for A3' }));
    await screen.findByTestId('todo-assign-picker');
    expect(screen.queryByRole('button', { name: 'Add new spool' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Scan label' })).toBeEnabled();
  });

  it('scanning shows the scanner in the entry and Back returns to the list', async () => {
    await open();
    fireEvent.click(screen.getByRole('button', { name: 'Scan label' }));
    expect(await screen.findByRole('button', { name: /take photo/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findAllByTestId('todo-assign-spool')).not.toHaveLength(0);
  });

  it('says so when no spool matches', async () => {
    server.use(http.get('/api/v1/inventory/spools', () => HttpResponse.json([])));
    setup();
    server.use(http.get('/api/v1/inventory/spools', () => HttpResponse.json([])));
    renderActions();
    fireEvent.click(await screen.findByRole('button', { name: 'Assign spool for A3' }));
    expect(await screen.findByTestId('todo-assign-none')).toHaveTextContent('No matching spool in the inventory.');
  });
});

describe('Spoolman mode', () => {
  const smSpool = (id: number, extra: Record<string, unknown> = {}) => spool(id, { ...extra });

  it('picks from the Spoolman spools, assigns through Spoolman, offers no new spool, and shows a dash for missing grams', async () => {
    const sent = setup({ spoolman: 'on', spoolmanSpools: [smSpool(41), smSpool(42, { label_weight: 0 })] });
    renderActions();
    fireEvent.click(await screen.findByRole('button', { name: 'Assign spool for A3' }));
    const rows = await screen.findAllByTestId('todo-assign-spool');
    expect(rows).toHaveLength(2);
    expect(rows[1]).toHaveTextContent('Polymaker PLA PolyTerra · —');
    expect(screen.queryByRole('button', { name: 'Add new spool' })).toBeNull();
    fireEvent.click(within(rows[0]).getByRole('button', { name: /Assign spool/ }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]).toEqual({ path: 'spoolman', body: { spoolman_spool_id: 41, printer_id: 7, ams_id: 0, tray_id: 2 } });
  });
});

describe('what happens while the list refetches', () => {
  it('keeps the picker open when the list hands over new slot objects', async () => {
    setup();
    const { rerender } = renderActions();
    fireEvent.click(await screen.findByRole('button', { name: 'Assign spool for A3' }));
    await screen.findByTestId('todo-assign-picker');
    // A refetch: equal data, new objects.
    const fresh: QueueTodoPicture = JSON.parse(JSON.stringify(picture));
    const client = new QueryClient();
    rerender(
      <QueryClientProvider client={client}>
        <MemoryRouter><ToastProvider><PictureActions picture={fresh} /></ToastProvider></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId('todo-assign-picker')).toBeInTheDocument();
  });
});

describe('putting the new spool in first', () => {
  const outPicture = (slotOverrides: Partial<QueueTodoPictureSlot>): QueueTodoPicture => ({
    ...picture,
    units: [{ ...picture.units[0], slots: [slot(2, { incoming, ...slotOverrides })] }],
  });

  it('says so above the picker for a slot whose old spool goes out', async () => {
    setup();
    renderActions(outPicture({ state: 'out' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Assign spool for A3' }));
    expect(await screen.findByTestId('todo-put-in-first')).toHaveTextContent('Put the new spool in first, then assign it.');
  });

  it('says so for a slot that still reports an RFID spool', async () => {
    setup();
    renderActions(outPicture({ state: 'keep', rfid: true }));
    fireEvent.click(await screen.findByRole('button', { name: 'Assign spool for A3' }));
    expect(await screen.findByTestId('todo-put-in-first')).toBeInTheDocument();
  });

  it('does not say it for an empty slot', async () => {
    setup();
    renderActions(outPicture({ type: '', color: '', state: 'empty' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Assign spool for A3' }));
    await screen.findByTestId('todo-assign-picker');
    expect(screen.queryByTestId('todo-put-in-first')).toBeNull();
  });
});

describe('before Spoolman is known', () => {
  it('offers no assigning until the status has answered', async () => {
    setup();
    server.use(
      http.get('/api/v1/spoolman/status', async () => {
        await new Promise((r) => setTimeout(r, 300));
        return HttpResponse.json({ enabled: false, connected: false, url: null });
      }),
    );
    renderActions();
    expect(screen.queryByRole('button', { name: 'Assign spool for A3' })).toBeNull();
    expect(await screen.findByRole('button', { name: 'Assign spool for A3' })).toBeInTheDocument();
  });
});
