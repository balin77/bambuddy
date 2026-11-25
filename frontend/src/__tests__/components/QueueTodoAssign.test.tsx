/**
 * Assigning a spool inside a To do entry (#3726): the menu a slot of the
 * picture opens, the shared picker's inline layout and who sees what.
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

import { PictureWithActions } from '../../components/QueueTodoSlotActions';

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
          <PictureWithActions picture={pic} filaments={[]} />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { invalidate, client, ...view };
}

// A slot of the picture is the button: named by its label, filament and state.
const slotButton = (label = 'A3') => screen.findByRole('button', { name: new RegExp(`^${label} - `) });

async function openSlotMenu(label = 'A3') {
  fireEvent.click(await slotButton(label));
  return screen.findByRole('menu');
}

async function chooseAssign(label = 'A3') {
  await openSlotMenu(label);
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Assign Spool' }));
}

beforeEach(() => {
  perms.granted = new Set(['inventory:update', 'inventory:create', 'printers:filament']);
  perms.hide = false;
});

describe('the slots of an entry with a picture', () => {
  it('has no row of buttons under the picture: the slots are the buttons', async () => {
    setup();
    renderActions();
    await slotButton();
    expect(screen.queryByRole('button', { name: /Assign spool for/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Set up slot/ })).toBeNull();
    // Nothing but the slots themselves: A1, A2, A3 and the empty A4.
    const buttons = screen.getAllByRole('button');
    expect(buttons.map((b) => b.dataset.testid)).toEqual(['todo-ams-slot', 'todo-ams-slot', 'todo-ams-slot', 'todo-ams-slot']);
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('opens the menu of the slot the filament goes into: assign a spool, then configure', async () => {
    setup();
    renderActions();
    const slotA3 = await slotButton();
    expect(slotA3).toHaveAttribute('aria-haspopup', 'menu');
    expect(slotA3).toHaveAttribute('aria-expanded', 'false');
    const menu = await openSlotMenu();
    expect(slotA3).toHaveAttribute('aria-expanded', 'true');
    expect(slotA3).toHaveAttribute('aria-controls', menu.id);
    await screen.findByRole('menuitem', { name: 'Assign Spool' });
    // The labels and the order of the printer card's slot menu.
    expect(within(menu).getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Assign Spool', 'Configure']);
    expect(within(menu).getByTestId('todo-ams-slot-menu-title')).toHaveTextContent('A3 · PLA Lava Red');
    // A second click on the slot closes it.
    fireEvent.click(slotA3);
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('assigning from the menu opens the picker for that slot with the filament of the entry', async () => {
    setup();
    renderActions();
    await chooseAssign();
    expect(screen.queryByRole('menu')).toBeNull();
    expect(await screen.findByRole('heading', { name: 'Which spool goes into A3?' })).toBeInTheDocument();
    expect(screen.getByText('PLA Lava Red from the inventory. The job needs 505 g.')).toBeInTheDocument();
  });

  it('closes the menu on a press outside it', async () => {
    setup();
    renderActions();
    await openSlotMenu();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('opens one menu at a time', async () => {
    setup();
    renderActions();
    await openSlotMenu('A3');
    await openSlotMenu('A1');
    expect(screen.getAllByRole('menu')).toHaveLength(1);
    expect(screen.getByTestId('todo-ams-slot-menu-title')).toHaveTextContent(/^A1/);
  });

  it('does not open on hover: a click, a tap or the keyboard', async () => {
    setup();
    renderActions();
    fireEvent.mouseEnter(await slotButton());
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('opens from the keyboard, moves between the items with the arrows, and Escape returns to the slot', async () => {
    setup();
    renderActions();
    const slotA3 = await slotButton();
    expect(slotA3).toHaveAttribute('tabindex', '0');
    await waitFor(() => expect(screen.getByTestId('todo-slot-menu-hint')).toHaveTextContent('Tap a slot to assign its spool.'));
    slotA3.focus();
    fireEvent.keyDown(slotA3, { key: 'Enter' });
    const assign = await screen.findByRole('menuitem', { name: 'Assign Spool' });
    const configure = screen.getByRole('menuitem', { name: 'Configure' });
    await waitFor(() => expect(assign).toHaveFocus());
    fireEvent.keyDown(assign, { key: 'ArrowDown' });
    expect(configure).toHaveFocus();
    fireEvent.keyDown(configure, { key: 'ArrowDown' });
    expect(assign).toHaveFocus();
    fireEvent.keyDown(assign, { key: 'End' });
    expect(configure).toHaveFocus();
    fireEvent.keyDown(configure, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
    expect(slotA3).toHaveFocus();
    // Space opens it as well.
    fireEvent.keyDown(slotA3, { key: ' ' });
    expect(await screen.findByRole('menu')).toBeInTheDocument();
  });

  it('gives the focus back to the slot when an item is chosen', async () => {
    setup();
    renderActions();
    const slotA3 = await slotButton();
    await chooseAssign();
    expect(slotA3).toHaveFocus();
  });

  it('sets no slot up that has an RFID spool', async () => {
    setup();
    renderActions({ ...picture, units: [{ ...picture.units[0], slots: [slot(2, { rfid: true, incoming })] }] });
    const menu = await openSlotMenu();
    await screen.findByRole('menuitem', { name: 'Assign Spool' });
    expect(within(menu).getAllByRole('menuitem')).toHaveLength(1);
  });

  it('makes the slot the running print uses no button', async () => {
    setup();
    renderActions({
      ...picture,
      units: [{ ...picture.units[0], slots: [slot(0, { state: 'locked' }), slot(1, { state: 'locked', incoming }), slot(2, { state: 'out', incoming })] }],
    });
    await slotButton('A3');
    const cards = screen.getAllByTestId('todo-ams-slot');
    for (const locked of cards.slice(0, 2)) {
      expect(locked).not.toHaveAttribute('role');
      expect(locked).not.toHaveAttribute('tabindex');
      expect(locked.className).not.toContain('cursor-pointer');
      fireEvent.click(locked);
    }
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.getAllByRole('button')).toHaveLength(1);
  });

  it('gives a slot nothing goes into the same menu, as on the printer card, but none over an RFID spool', async () => {
    setup();
    renderActions({
      ...picture,
      units: [{ ...picture.units[0], slots: [slot(0), slot(1, { rfid: true }), slot(2, { state: 'out', incoming }), slot(3, { type: '', color: '', state: 'empty' })] }],
    });
    await screen.findByTestId('todo-slot-menu-hint');
    const cards = screen.getAllByTestId('todo-ams-slot');
    expect(cards.map((c) => c.getAttribute('role'))).toEqual(['button', null, 'button', 'button']);
    // A kept slot: its own filament comes first in the picker, no "put in first".
    await chooseAssign('A1');
    expect(await screen.findByRole('heading', { name: 'Which spool goes into A1?' })).toBeInTheDocument();
    expect(screen.queryByTestId('todo-put-in-first')).toBeNull();
    // An empty one: every spool.
    await chooseAssign('A4');
    expect(await screen.findByRole('heading', { name: 'Which spool goes into A4?' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByTestId('todo-assign-spool')).toHaveLength(4));
  });

  it('marks a slot that opens a menu, and looks like a button', async () => {
    setup();
    renderActions({ ...picture, units: [{ ...picture.units[0], slots: [slot(0, { state: 'locked' }), slot(2, { state: 'out', incoming })] }] });
    const slotA3 = await slotButton();
    expect(slotA3.className).toContain('cursor-pointer');
    expect(slotA3.className).toContain('focus-visible:ring-2');
    expect(slotA3.className).toContain('hover:ring-2');
    expect(screen.getAllByTestId('todo-ams-slot-menu-mark')).toHaveLength(1);
  });

  it('has no button for who holds no permission and whose groups hide what they cannot use, and no hint', () => {
    setup();
    perms.granted = new Set();
    perms.hide = true;
    const { container } = renderActions();
    expect(screen.getAllByTestId('todo-ams-slot')).toHaveLength(4);
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByTestId('todo-slot-menu-hint')).toBeNull();
    expect(container.querySelector('[data-testid="todo-slot-actions"]')).toBeNull();
  });

  it('greys the items out, with the reason, for who may not use them, and gives no hint', async () => {
    setup();
    perms.granted = new Set();
    renderActions();
    await openSlotMenu();
    const assign = screen.getByRole('menuitem', { name: 'Assign Spool' });
    expect(assign).toBeDisabled();
    expect(assign).toHaveAttribute('title', 'You do not have permission to assign spools');
    const configure = screen.getByRole('menuitem', { name: 'Configure' });
    expect(configure).toBeDisabled();
    expect(configure).toHaveAttribute('title', 'You do not have permission to set up AMS slots');
    fireEvent.click(assign);
    expect(screen.queryByTestId('todo-assign-picker')).toBeNull();
    expect(screen.queryByTestId('todo-slot-menu-hint')).toBeNull();
  });

  it('assigns with inventory:update alone and sets up with printers:filament alone (hide option on)', async () => {
    setup();
    perms.hide = true;
    perms.granted = new Set(['inventory:update']);
    const { unmount } = renderActions();
    let menu = await openSlotMenu();
    expect(within(menu).getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Assign Spool']);
    expect(screen.getByRole('menuitem', { name: 'Assign Spool' })).toBeEnabled();
    expect(screen.getByTestId('todo-slot-menu-hint')).toHaveTextContent('Tap a slot to assign its spool.');
    unmount();
    perms.granted = new Set(['printers:filament']);
    renderActions();
    menu = await openSlotMenu();
    expect(within(menu).getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Configure']);
    expect(screen.getByRole('menuitem', { name: 'Configure' })).toBeEnabled();
    expect(screen.getByTestId('todo-slot-menu-hint')).toHaveTextContent('Tap a slot to set it up.');
  });

  it('makes a slot no button when the hide option leaves its menu empty', async () => {
    setup();
    perms.hide = true;
    perms.granted = new Set(['printers:filament']);
    // Nothing is set up over an RFID spool, and assigning is hidden.
    renderActions({ ...picture, units: [{ ...picture.units[0], slots: [slot(2, { rfid: true, state: 'out', incoming })] }] });
    expect(screen.getByTestId('todo-ams-slot')).not.toHaveAttribute('role');
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByTestId('todo-slot-menu-hint')).toBeNull();
  });

  it('does not take printers:control for the slot set-up: only printers:filament', async () => {
    setup();
    perms.granted = new Set(['printers:control']);
    renderActions();
    await openSlotMenu();
    expect(screen.getByRole('menuitem', { name: 'Configure' })).toBeDisabled();
  });

  it('makes every item of the menu at least 44 px high on a phone', async () => {
    setup();
    renderActions();
    await openSlotMenu();
    await screen.findByRole('menuitem', { name: 'Assign Spool' });
    for (const item of screen.getAllByRole('menuitem')) expect(item.className).toContain('min-h-[44px]');
  });

  it('keeps the menu inside the viewport of a phone', async () => {
    setup();
    renderActions();
    const menu = await openSlotMenu();
    expect(menu).toHaveStyle({ maxWidth: 'calc(100vw - 16px)' });
    expect(menu.className).toContain('fixed');
    // Placed from the slot's position: never left of the 8 px margin.
    expect(parseFloat(menu.style.left)).toBeGreaterThanOrEqual(8);
  });

  it('offers no assigning while Spoolman is down', async () => {
    setup({ spoolman: 'down' });
    const { client } = renderActions();
    // The status has answered (it is in the cache): only then is "no item" a statement about Spoolman being down.
    await waitFor(() => expect(client.getQueryData(['spoolman-status'])).toBeDefined());
    const menu = await openSlotMenu();
    expect(within(menu).getAllByRole('menuitem').map((i) => i.textContent)).toEqual(['Configure']);
    expect(screen.getByTestId('todo-slot-menu-hint')).toHaveTextContent('Tap a slot to set it up.');
  });
});

describe('the spools of the inventory inside the entry', () => {
  async function open() {
    const sent = setup();
    const view = renderActions();
    await chooseAssign();
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
    // The picker closes and the hint is back.
    await waitFor(() => expect(screen.queryByTestId('todo-assign-picker')).toBeNull());
    expect(await screen.findByTestId('todo-slot-menu-hint')).toBeInTheDocument();
  });

  it('shows every spool when asked, and Back returns to the picture', async () => {
    await open();
    fireEvent.click(screen.getByLabelText('Show all spools'));
    expect(screen.getAllByTestId('todo-assign-spool')).toHaveLength(4);
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.queryByTestId('todo-assign-picker')).toBeNull();
    expect(screen.getByTestId('todo-slot-menu-hint')).toBeInTheDocument();
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
    await chooseAssign();
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
    await chooseAssign();
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
    await chooseAssign();
    expect(await screen.findByTestId('todo-assign-none')).toHaveTextContent('No matching spool in the inventory.');
  });
});

describe('Spoolman mode', () => {
  const smSpool = (id: number, extra: Record<string, unknown> = {}) => spool(id, { ...extra });

  it('picks from the Spoolman spools, assigns through Spoolman, offers no new spool, and shows a dash for missing grams', async () => {
    const sent = setup({ spoolman: 'on', spoolmanSpools: [smSpool(41), smSpool(42, { label_weight: 0 })] });
    renderActions();
    await chooseAssign();
    const rows = await screen.findAllByTestId('todo-assign-spool');
    expect(rows).toHaveLength(2);
    expect(rows[1]).toHaveTextContent('Polymaker PLA PolyTerra · —');
    expect(screen.queryByRole('button', { name: 'Add new spool' })).toBeNull();
    fireEvent.click(within(rows[0]).getByRole('button', { name: /Assign spool/ }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]).toEqual({ path: 'spoolman', body: { spoolman_spool_id: 41, printer_id: 7, ams_id: 0, tray_id: 2 } });
  });
});

describe('Spoolman mode: scan, errors and Spoolman going down', () => {
  const smSpool = (id: number) => spool(id);

  // The photo fallback with a stubbed decoder: jsdom has no camera.
  function scanLabel(rawValue: string) {
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ width: 10, height: 10, close: vi.fn() }));
    vi.stubGlobal('BarcodeDetector', class { detect = vi.fn().mockResolvedValue([{ rawValue }]); });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['qr'], 'qr.jpg', { type: 'image/jpeg' })] } });
  }

  it('a scanned Spoolman label assigns that spool to the slot of the entry, moving it', async () => {
    const sent = setup({ spoolman: 'on', spoolmanSpools: [smSpool(41)] });
    renderActions();
    await chooseAssign();
    await screen.findAllByTestId('todo-assign-spool');
    fireEvent.click(screen.getByRole('button', { name: 'Scan label' }));
    await screen.findByRole('button', { name: /take photo/i });
    scanLabel('web+spoolman:s-12');
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]).toEqual({ path: 'spoolman', body: { spoolman_spool_id: 12, printer_id: 7, ams_id: 0, tray_id: 2, move: true } });
    // Nothing went to the built-in inventory.
    expect(sent.some((s) => s.path === 'assign')).toBe(false);
  });

  it('shows the error toast and keeps the picker open when Spoolman refuses the assign', async () => {
    const sent = setup({ spoolman: 'on', spoolmanSpools: [smSpool(41)] });
    server.use(
      http.post('/api/v1/spoolman/inventory/slot-assignments', async ({ request }) => {
        sent.push({ path: 'spoolman', body: await request.json() });
        return HttpResponse.json({ detail: 'Spoolman server is not reachable' }, { status: 502 });
      }),
    );
    const { invalidate } = renderActions();
    await chooseAssign();
    const rows = await screen.findAllByTestId('todo-assign-spool');
    fireEvent.click(within(rows[0]).getByRole('button', { name: /Assign spool/ }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(await screen.findByText(/Failed to assign spool: Spoolman server is not reachable/)).toBeInTheDocument();
    expect(screen.getByTestId('todo-assign-picker')).toBeInTheDocument();
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: ['queue-todo'] });
  });

  it('stops assigning when Spoolman goes down while the picker is open', async () => {
    const sent = setup({ spoolman: 'on', spoolmanSpools: [smSpool(41)] });
    const { client } = renderActions();
    await chooseAssign();
    await screen.findAllByTestId('todo-assign-spool');
    // Spoolman stops answering; the status is asked again.
    server.use(
      http.get('/api/v1/spoolman/status', () => HttpResponse.json({ enabled: true, connected: false, url: 'http://sm' })),
    );
    await client.invalidateQueries({ queryKey: ['spoolman-status'] });
    // Wait for the answer "down" to be in the cache, so that "no picker" is not just "not loaded yet".
    await waitFor(() => expect(client.getQueryData<{ connected: boolean }>(['spoolman-status'])?.connected).toBe(false));
    await waitFor(() => expect(screen.queryByTestId('todo-assign-spool')).toBeNull());
    expect(screen.queryByRole('button', { name: /Assign spool/ })).toBeNull();
    // The slot's menu no longer assigns either.
    await openSlotMenu();
    expect(screen.queryByRole('menuitem', { name: 'Assign Spool' })).toBeNull();
    expect(screen.getByRole('menuitem', { name: 'Configure' })).toBeInTheDocument();
    // The built-in inventory is not offered in its place.
    expect(sent).toHaveLength(0);
  });
});

describe('what happens while the list refetches', () => {
  it('keeps the picker open when the list hands over new slot objects', async () => {
    setup();
    const { rerender } = renderActions();
    await chooseAssign();
    await screen.findByTestId('todo-assign-picker');
    // A refetch: equal data, new objects.
    const fresh: QueueTodoPicture = JSON.parse(JSON.stringify(picture));
    const client = new QueryClient();
    rerender(
      <QueryClientProvider client={client}>
        <MemoryRouter><ToastProvider><PictureWithActions picture={fresh} filaments={[]} /></ToastProvider></MemoryRouter>
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
    await chooseAssign();
    expect(await screen.findByTestId('todo-put-in-first')).toHaveTextContent('Put the new spool in first, then assign it.');
  });

  it('says so for a slot that still reports an RFID spool', async () => {
    setup();
    renderActions(outPicture({ state: 'keep', rfid: true }));
    await chooseAssign();
    expect(await screen.findByTestId('todo-put-in-first')).toBeInTheDocument();
  });

  it('does not say it for an empty slot', async () => {
    setup();
    renderActions(outPicture({ type: '', color: '', state: 'empty' }));
    await chooseAssign();
    await screen.findByTestId('todo-assign-picker');
    expect(screen.queryByTestId('todo-put-in-first')).toBeNull();
  });
});

describe('before Spoolman is known', () => {
  it('offers no assigning until the status has answered', async () => {
    setup();
    // The answer is held back until the test lets it go: no clock involved.
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    let asked = false;
    server.use(
      http.get('/api/v1/spoolman/status', async () => {
        asked = true;
        await gate;
        return HttpResponse.json({ enabled: false, connected: false, url: null });
      }),
    );
    renderActions();
    await waitFor(() => expect(asked).toBe(true));
    await openSlotMenu();
    expect(screen.queryByRole('menuitem', { name: 'Assign Spool' })).toBeNull();
    // Setting the slot up does not wait for Spoolman: offered, and still no assign.
    expect(screen.getByRole('menuitem', { name: 'Configure' })).toBeInTheDocument();
    expect(screen.getByTestId('todo-slot-menu-hint')).toHaveTextContent('Tap a slot to set it up.');
    release();
    expect(await screen.findByRole('menuitem', { name: 'Assign Spool' })).toBeInTheDocument();
    expect(screen.getByTestId('todo-slot-menu-hint')).toHaveTextContent('Tap a slot to assign its spool.');
  });
});
