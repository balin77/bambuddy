/**
 * "To do" list of what the queue waits on (#3615): list rendering per kind,
 * merged entries, empty state, nav badge, actions and their permissions.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, waitFor, fireEvent, render as rtlRender, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '../../contexts/ToastContext';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import i18n from '../../i18n';
import { setColorCatalog, __resetColorCatalogForTests } from '../../utils/colors';
import type { QueueTodo, QueueTodoEntry, QueueTodoHintSlot, QueueTodoPaused, QueueTodoPausedSlot, QueueTodoPrepare, QueueTodoSlotHint } from '../../api/client';

const perms = { granted: new Set<string>() };

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
      hasAnyPermission: (...ps: string[]) => ps.some((p) => perms.granted.has(p)),
      canModify: () => true,
    }),
  };
});

import { QueueTodoList } from '../../components/QueueTodoList';
import { QueueTodoLauncher } from '../../components/QueueTodoLauncher';
import { useQueueTodoAutoRefresh } from '../../hooks/useQueueTodo';

const todo: QueueTodo = {
  count: 6,
  groups: [
    {
      printer_id: 1,
      printer_name: 'Alpha',
      target_model: null,
      entries: [
        { kind: 'plate_clear', jobs: [{ id: 10, name: 'Benchy', can_start: false }], filaments: [], printers: [], detail: null },
        { kind: 'sensor_interlock', jobs: [{ id: 10, name: 'Benchy', can_start: true }], detail: 'Enclosure Door', filaments: [], printers: [] },
        { kind: 'power_on_failed', jobs: [{ id: 10, name: 'Benchy', can_start: false }], filaments: [], printers: [], detail: null },
        {
          kind: 'load_filament',
          jobs: [
            { id: 11, name: 'A', can_start: true },
            { id: 12, name: 'B', can_start: true },
            { id: 13, name: 'C', can_start: true },
          ],
          filaments: [{ type: 'PLA', color: '#FF0000', color_name: 'Red', no_stock: true }],
          printers: [],
          detail: null,
        },
        { kind: 'start_staged', jobs: [{ id: 14, name: 'Staged job', can_start: true }], filaments: [], printers: [], detail: null },
      ],
    },
    {
      printer_id: null,
      printer_name: 'X1C',
      target_model: 'X1C',
      entries: [
        { kind: 'load_filament', jobs: [{ id: 20, name: 'Model job', can_start: true }], filaments: [{ type: 'PETG', color: '#00FF00', color_name: '', no_stock: false }], printers: [{ id: 5, name: 'A1-01' }, { id: 6, name: 'A1-02' }], detail: null },
      ],
    },
  ],
};

beforeEach(() => {
  perms.granted = new Set(['printers:clear_plate', 'queue:update_all', 'queue:read_all']);
});

describe('QueueTodoList', () => {
  it('renders every kind with details, merged job count and model group', () => {
    render(<QueueTodoList todo={todo} />);
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Any X1C')).toBeInTheDocument();
    expect(screen.getByTestId('todo-entry-plate_clear')).toBeInTheDocument();
    expect(screen.getByTestId('todo-entry-sensor_interlock')).toHaveTextContent('Enclosure Door');
    expect(screen.getByTestId('todo-entry-power_on_failed')).toBeInTheDocument();
    expect(screen.getByTestId('todo-entry-start_staged')).toHaveTextContent('Staged job');
    // Merged entry: 3 jobs -> a count, one swatch, red "no stock" hint.
    const load = screen.getAllByTestId('todo-entry-load_filament')[0];
    expect(load).toHaveTextContent('3 jobs');
    expect(load).toHaveTextContent('PLA Red');
    expect(load).toHaveTextContent('none left in inventory');
    expect(screen.getAllByTestId('todo-swatch')).toHaveLength(2);
  });

  it('names the nozzle of a dual-nozzle filament, and none otherwise', () => {
    const black = { type: 'PETG', color: '#000000', color_name: 'Black', no_stock: false };
    const dual: QueueTodo = {
      count: 1,
      groups: [{
        printer_id: 1,
        printer_name: 'H2D',
        target_model: null,
        entries: [{
          kind: 'load_filament',
          jobs: [{ id: 30, name: 'Dual', can_start: false }],
          filaments: [{ ...black, nozzle: 0 }, { ...black, nozzle: 1 }, { ...black, nozzle: null }, black],
          printers: [],
          detail: null,
        }],
      }],
    };
    render(<QueueTodoList todo={dual} />);
    expect(screen.getAllByTestId('todo-nozzle').map((n) => n.textContent)).toEqual(['(Right nozzle)', '(Left nozzle)']);
  });

  it('renders nothing when empty', () => {
    const { container } = render(<QueueTodoList todo={{ count: 0, groups: [] }} />);
    expect(container.querySelector('[data-testid="queue-todo-list"]')).toBeNull();
  });

  it('leaves out a printer group without entries', () => {
    const mixed: QueueTodo = {
      count: 1,
      groups: [
        { printer_id: 1, printer_name: 'Empty printer', target_model: null, entries: [] },
        {
          printer_id: 2,
          printer_name: 'Busy printer',
          target_model: null,
          entries: [{ kind: 'plate_clear', jobs: [{ id: 10, name: 'Benchy', can_start: false }], filaments: [], printers: [], detail: null }],
        },
      ],
    };
    const { container } = render(<QueueTodoList todo={mixed} />);
    expect(container.querySelectorAll('section')).toHaveLength(1);
    expect(screen.queryByText('Empty printer')).toBeNull();
    expect(screen.getByText('Busy printer')).toBeTruthy();
  });

  it('links filament/interlock entries to the printer or the queue', () => {
    render(<QueueTodoList todo={todo} />);
    const links = screen.getAllByRole('link');
    expect(links.some((l) => l.getAttribute('href') === '/printers#printer-card-1')).toBe(true);
    expect(links.some((l) => l.getAttribute('href') === '/queue')).toBe(true);
  });

  it('plate is clear calls the clear-plate API', async () => {
    const called = vi.fn();
    server.use(
      http.post('/api/v1/printers/1/clear-plate', () => {
        called();
        return HttpResponse.json({ success: true, message: 'ok' });
      }),
    );
    render(<QueueTodoList todo={todo} />);
    fireEvent.click(screen.getByRole('button', { name: 'Plate is clear' }));
    await waitFor(() => expect(called).toHaveBeenCalled());
  });

  it('start calls the queue start API', async () => {
    const called = vi.fn();
    server.use(
      http.post('/api/v1/queue/14/start', () => {
        called();
        return HttpResponse.json({ id: 14 });
      }),
    );
    render(<QueueTodoList todo={todo} />);
    fireEvent.click(screen.getByRole('button', { name: /Start Print/ }));
    await waitFor(() => expect(called).toHaveBeenCalled());
  });

  it('disables plate-clear without permission', () => {
    perms.granted = new Set();
    render(<QueueTodoList todo={todo} />);
    expect(screen.getByRole('button', { name: 'Plate is clear' })).toBeDisabled();
  });

  it('start follows the per-job can_start with the permission reason as tooltip', () => {
    const blocked: QueueTodo = {
      count: 1,
      groups: [{
        printer_id: 1, printer_name: 'Alpha', target_model: null,
        entries: [{ kind: 'start_staged', jobs: [{ id: 14, name: 'Staged job', can_start: false }], filaments: [], printers: [], detail: null }],
      }],
    };
    perms.granted = new Set(['queue:update_own']);
    const { unmount } = render(<QueueTodoList todo={blocked} />);
    const btn = screen.getByRole('button', { name: /Start Print/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('title', expect.stringMatching(/Waiting for review/));
    unmount();
    perms.granted = new Set(['queue:update_all']);
    render(<QueueTodoList todo={blocked} />);
    expect(screen.getByRole('button', { name: /Start Print/ })).toHaveAttribute('title', expect.stringMatching(/permission/i));
  });

  it('keeps the translated start failure and adds a 4xx string detail; none for a 5xx', async () => {
    server.use(
      http.post('/api/v1/queue/14/start', () => HttpResponse.json({ detail: 'Printer is busy' }, { status: 500 })),
    );
    render(<QueueTodoList todo={todo} />);
    fireEvent.click(screen.getByRole('button', { name: /Start Print/ }));
    expect(await screen.findByText('Failed to start print')).toBeInTheDocument();
    expect(screen.queryByText(/Printer is busy/)).toBeNull();
  });

  it('shows the backend error message when starting fails', async () => {
    server.use(
      http.post('/api/v1/queue/14/start', () => HttpResponse.json({ detail: 'Printer is busy' }, { status: 400 })),
    );
    render(<QueueTodoList todo={todo} />);
    fireEvent.click(screen.getByRole('button', { name: /Start Print/ }));
    expect(await screen.findByText('Failed to start print (Printer is busy)')).toBeInTheDocument();
  });

  it('asks for confirmation on a filament shortage and resends with skip_filament_check', async () => {
    const calls: string[] = [];
    server.use(
      http.post('/api/v1/queue/14/start', ({ request }) => {
        const url = new URL(request.url);
        calls.push(url.search);
        if (url.searchParams.get('skip_filament_check')) return HttpResponse.json({ id: 14 });
        return HttpResponse.json(
          { detail: { code: 'insufficient_filament', message: 'short', deficit: [{ slot_id: 1, required_grams: 50, remaining_grams: 10 }] } },
          { status: 409 },
        );
      }),
    );
    render(<QueueTodoList todo={todo} />);
    fireEvent.click(screen.getByRole('button', { name: /Start Print/ }));
    fireEvent.click(await screen.findByRole('button', { name: /Print Anyway/i }));
    await waitFor(() => expect(calls).toEqual(['', '?skip_filament_check=true']));
  });

  it('asks for confirmation on an unmatched filament too', async () => {
    server.use(
      http.post('/api/v1/queue/14/start', ({ request }) =>
        new URL(request.url).searchParams.get('skip_filament_check')
          ? HttpResponse.json({ id: 14 })
          : HttpResponse.json({ detail: { code: 'unmatched_filament', message: 'x', missing: ['PLA Red'] } }, { status: 409 }),
      ),
    );
    render(<QueueTodoList todo={todo} />);
    fireEvent.click(screen.getByRole('button', { name: /Start Print/ }));
    expect(await screen.findByText(/PLA Red/)).toBeInTheDocument();
  });

  it('renders a model-group load entry with links to the printers', () => {
    render(<QueueTodoList todo={todo} />);
    const entry = screen.getAllByTestId('todo-entry-load_filament')[1];
    expect(entry).toHaveTextContent('Load filament on A1-01 or A1-02');
    expect(screen.getByRole('link', { name: 'A1-01' })).toHaveAttribute('href', '/printers#printer-card-5');
    expect(screen.getByRole('link', { name: 'A1-02' })).toHaveAttribute('href', '/printers#printer-card-6');
  });

  it('labels a swatch with its colour when the name is empty', () => {
    render(<QueueTodoList todo={todo} />);
    expect(screen.getByLabelText('#00FF00')).toHaveAttribute('title', '#00FF00');
  });

  it('truncates long job names and keeps the full name reachable', () => {
    const long = 'L'.repeat(200);
    const t2: QueueTodo = {
      count: 1,
      groups: [{
        printer_id: 1, printer_name: 'Alpha', target_model: null,
        entries: [{ kind: 'start_staged', jobs: [{ id: 14, name: long, can_start: true }], filaments: [], printers: [], detail: null }],
      }],
    };
    render(<QueueTodoList todo={t2} />);
    const btn = screen.getByRole('button', { name: /Start Print/ });
    expect(btn.className).toMatch(/max-w-full/);
    expect(btn.className).toMatch(/min-w-0/);
    expect(btn.querySelector('span.truncate')).not.toBeNull();
    expect(screen.getByTitle(long)).toBeInTheDocument();
  });

  it('shows the heading when asked and no queue link on /queue', () => {
    rtlRender(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/queue']}>
          <ToastProvider><QueueTodoList todo={todo} heading /></ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole('heading', { name: 'To do', level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open queue' })).toBeNull();
  });
});

describe('QueueTodoList farm entries (#3575, #3587, #3590)', () => {
  const entry = (over: Partial<QueueTodo['groups'][0]['entries'][0]>) => ({
    kind: 'load_filament' as const,
    jobs: [{ id: 30, name: 'Job', can_start: false }],
    filaments: [],
    printers: [],
    detail: null,
    priority: null,
    priority_hours: null,
    plate_capacity: null,
    ...over,
  });
  const one = (e: ReturnType<typeof entry>): QueueTodo => ({
    count: 1,
    groups: [{ printer_id: 2, printer_name: 'Beta', target_model: null, entries: [e] }],
  });

  it('shows an empty plate changer with the refill action behind a confirmation', async () => {
    const called = vi.fn();
    server.use(
      http.post('/api/v1/printers/2/refill-plates', () => {
        called();
        return HttpResponse.json({ id: 2, plate_capacity: 12, plates_remaining: 12 });
      }),
    );
    render(<QueueTodoList todo={one(entry({ kind: 'plate_changer_empty', plate_capacity: 12 }))} />);
    expect(screen.getByTestId('todo-entry-plate_changer_empty')).toHaveTextContent('Plate changer empty');
    fireEvent.click(screen.getByRole('button', { name: 'Refilled / Emptied' }));
    // Nothing happens on a stray tap: the printer card's confirmation comes first.
    expect(called).not.toHaveBeenCalled();
    expect(screen.getByText(/The count goes back to 12/)).toBeInTheDocument();
    const confirm = screen.getAllByRole('button', { name: 'Refilled / Emptied' }).pop() as HTMLElement;
    fireEvent.click(confirm);
    await waitFor(() => expect(called).toHaveBeenCalled());
  });

  it('can be cancelled without refilling', () => {
    const called = vi.fn();
    server.use(
      http.post('/api/v1/printers/2/refill-plates', () => {
        called();
        return HttpResponse.json({});
      }),
    );
    render(<QueueTodoList todo={one(entry({ kind: 'plate_changer_empty', plate_capacity: 12 }))} />);
    fireEvent.click(screen.getByRole('button', { name: 'Refilled / Emptied' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(called).not.toHaveBeenCalled();
  });

  it('disables the refill without the plate-clear permission', () => {
    perms.granted = new Set();
    render(<QueueTodoList todo={one(entry({ kind: 'plate_changer_empty', plate_capacity: 12 }))} />);
    expect(screen.getByRole('button', { name: 'Refilled / Emptied' })).toBeDisabled();
  });

  it('shows priority in N h and has priority for a filament wait', () => {
    const { unmount } = render(
      <QueueTodoList
        todo={one(entry({ filaments: [{ type: 'PLA', color: '', color_name: '', no_stock: false }], priority: 'priority_in', priority_hours: 38 }))}
      />,
    );
    expect(screen.getByTestId('todo-priority')).toHaveTextContent('priority in 38 h');
    unmount();
    render(
      <QueueTodoList
        todo={one(entry({ filaments: [{ type: 'PLA', color: '', color_name: '', no_stock: false }], priority: 'has_priority' }))}
      />,
    );
    expect(screen.getByTestId('todo-priority')).toHaveTextContent('has priority');
  });

  it('shows no priority line without one', () => {
    render(<QueueTodoList todo={one(entry({ filaments: [{ type: 'PLA', color: '', color_name: '', no_stock: false }] }))} />);
    expect(screen.queryByTestId('todo-priority')).toBeNull();
  });

  it('shows none left in inventory only for a flagged filament', () => {
    render(
      <QueueTodoList
        todo={one(
          entry({
            filaments: [
              { type: 'PLA', color: '#FF0000', color_name: 'Red', no_stock: true },
              { type: 'PETG', color: '#0000FF', color_name: 'Blue', no_stock: false },
            ],
          }),
        )}
      />,
    );
    expect(screen.getAllByText('(none left in inventory)')).toHaveLength(1);
  });
});

describe('QueueTodoList slot hints (#3634)', () => {
  const slot = (tray_id: number, type = '', color = '', extra: Partial<QueueTodoHintSlot> = {}): QueueTodoHintSlot => ({
    ams_id: 0, tray_id, is_ht: false, is_external: false, ams_type: 1, nozzle: null, type, color, tray_info_idx: '', tray_sub_brands: '', ...extra,
  });
  const hint = (state: QueueTodoSlotHint['state'], slots: QueueTodoHintSlot[] = [], extra: Partial<QueueTodoSlotHint> = {}): QueueTodoSlotHint => ({
    state, slots, unknown_jobs: 0, by_nozzle: [], ...extra,
  });
  const pink = { type: 'PLA', color: '#FF69B4', color_name: 'Pink', no_stock: false };
  const pinned = (slot_hint: QueueTodoSlotHint | null): QueueTodo => ({
    count: 1,
    groups: [{
      printer_id: 1, printer_name: 'Farm-A1', target_model: null,
      entries: [{ kind: 'load_filament', jobs: [{ id: 1, name: 'Job', can_start: false }], filaments: [pink], printers: [], detail: null, slot_hint }],
    }],
  });

  it('names a free slot', () => {
    render(<QueueTodoList todo={pinned(hint('free', [slot(1), slot(3)]))} />);
    expect(screen.getByTestId('todo-slot-hint')).toHaveTextContent('Free: A2, A4');
  });

  it('names the replaceable slots with their filament', () => {
    render(<QueueTodoList todo={pinned(hint('replaceable', [slot(3, 'PLA', '#00FF00'), slot(0, 'PETG', '#000000', { ams_id: 1 })]))} />);
    const text = screen.getByTestId('todo-slot-hint').textContent ?? '';
    expect(text).toMatch(/^Can be replaced: A4 \(PLA \w+/);
    expect(text).toContain('B1 (PETG ');
  });

  it('labels AMS-HT, 3H and the external holder like the printer card', () => {
    render(<QueueTodoList todo={pinned(hint('free', [
      slot(0, '', '', { ams_id: 128, tray_id: 0, is_ht: true, ams_type: 4 }),
      slot(2, '', '', { ams_id: 32, ams_type: 6 }),
      slot(0, '', '', { ams_id: 255, is_external: true, ams_type: null }),
    ]))} />);
    expect(screen.getByTestId('todo-slot-hint')).toHaveTextContent('Free: HT-A, 3H-3, Ext');
  });

  it('says when every loaded filament is needed', () => {
    render(<QueueTodoList todo={pinned(hint('all_needed'))} />);
    expect(screen.getByTestId('todo-slot-hint')).toHaveTextContent('Every loaded filament is needed by a waiting job');
  });

  it('adds the jobs whose filaments are unknown, singular and plural', () => {
    const { unmount } = render(<QueueTodoList todo={pinned(hint('free', [slot(1)], { unknown_jobs: 1 }))} />);
    expect(screen.getByTestId('todo-slot-hint')).toHaveTextContent('1 waiting job has unknown filaments');
    unmount();
    render(<QueueTodoList todo={pinned(hint('free', [slot(1)], { unknown_jobs: 2 }))} />);
    expect(screen.getByTestId('todo-slot-hint')).toHaveTextContent('2 waiting jobs have unknown filaments');
  });

  it('shows nothing without a hint', () => {
    render(<QueueTodoList todo={pinned(null)} />);
    expect(screen.queryByTestId('todo-slot-hint')).toBeNull();
    expect(screen.queryByTestId('todo-slot-hints')).toBeNull();
  });

  it('prefixes the nozzle when the filaments go on different nozzles', () => {
    const h = hint('free', [slot(1, '', '', { nozzle: 'left' })], {
      by_nozzle: [
        { nozzle: 'right', state: 'all_needed', slots: [] },
        { nozzle: 'left', state: 'free', slots: [slot(1, '', '', { nozzle: 'left' })] },
      ],
    });
    render(<QueueTodoList todo={pinned(h)} />);
    const text = screen.getByTestId('todo-slot-hint').textContent ?? '';
    expect(text).toContain('Right nozzle: Every loaded filament is needed by a waiting job');
    expect(text).toContain('Left nozzle: Free: A2');
  });

  it('puts no nozzle prefix on a printer without nozzle parts', () => {
    render(<QueueTodoList todo={pinned(hint('free', [slot(1, '', '', { nozzle: 'left' })]))} />);
    expect(screen.getByTestId('todo-slot-hint').textContent).toBe('Free: A2');
  });

  it('names the nozzle as soon as the hint has one part, never a combined state', () => {
    const only = { nozzle: 'left' as const, state: 'free' as const, slots: [slot(1, '', '', { nozzle: 'left' })] };
    render(<QueueTodoList todo={pinned(hint('free', only.slots, { by_nozzle: [only] }))} />);
    expect(screen.getByTestId('todo-slot-hint').textContent).toBe('Left nozzle: Free: A2');
  });

  describe('colour names', () => {
    beforeEach(() => {
      setColorCatalog(
        { '00ff00': 'Lime' },
        { 'pla basic|00ff00': 'Bambu Green' },
        [],
        { GFA00: 'pla basic' },
      );
    });
    afterEach(() => __resetColorCatalogForTests());

    it('does not pass the material type as the range: the preset names it', () => {
      // Nothing from RFID (no sub brand), only the preset the printer shows.
      render(<QueueTodoList todo={pinned(hint('replaceable', [slot(3, 'PLA', '#00FF00', { tray_info_idx: 'GFA00' })]))} />);
      expect(screen.getByTestId('todo-slot-hint')).toHaveTextContent('A4 (PLA Bambu Green)');
    });

    it('uses the sub brand of the tray as the range', () => {
      render(<QueueTodoList todo={pinned(hint('replaceable', [slot(3, 'PLA', '#00FF00', { tray_sub_brands: 'PLA Basic' })]))} />);
      expect(screen.getByTestId('todo-slot-hint')).toHaveTextContent('A4 (PLA Bambu Green)');
    });

    it('falls back to the plain catalogue without either', () => {
      render(<QueueTodoList todo={pinned(hint('replaceable', [slot(3, 'PLA', '#00FF00')]))} />);
      expect(screen.getByTestId('todo-slot-hint')).toHaveTextContent('A4 (PLA Lime)');
    });
  });

  describe('plurals and separators in other languages', () => {
    afterEach(async () => {
      await i18n.changeLanguage('en');
    });

    it.each([2, 5])('says "unknown filaments" in Russian for %i jobs, not in English', async (count) => {
      await i18n.loadLanguages('ru');
      await i18n.changeLanguage('ru');
      render(<QueueTodoList todo={pinned(hint('free', [slot(1)], { unknown_jobs: count }))} />);
      const text = screen.getByTestId('todo-slot-hint').textContent ?? '';
      expect(text).toContain(`Ожидающие задания с неизвестным филаментом: ${count}`);
      expect(text).not.toContain('waiting jobs');
    });

    it('uses the localised separator: French puts a space before the colon', async () => {
      await i18n.loadLanguages('fr');
      await i18n.changeLanguage('fr');
      const only = { nozzle: 'left' as const, state: 'free' as const, slots: [slot(1, '', '', { nozzle: 'left' })] };
      render(<QueueTodoList todo={pinned(hint('free', only.slots, { by_nozzle: [only] }))} />);
      expect(screen.getByTestId('todo-slot-hint').textContent).toBe('Buse gauche : Libres : A2');
    });

    it('uses the full-width colon in Chinese', async () => {
      await i18n.loadLanguages('zh-CN');
      await i18n.changeLanguage('zh-CN');
      const only = { nozzle: 'right' as const, state: 'all_needed' as const, slots: [] };
      render(<QueueTodoList todo={pinned(hint('all_needed', [], { by_nozzle: [only] }))} />);
      expect(screen.getByTestId('todo-slot-hint').textContent).toMatch(/^.+：.+/);
      expect(screen.getByTestId('todo-slot-hint').textContent).not.toContain(': ');
    });

    it.each([
      ['pl', 'Wolne: A2'],
      ['es', 'Libres: A2'],
      ['it', 'Liberi: A2'],
    ])('uses the plural for free slots in %s', async (lang, expected) => {
      await i18n.loadLanguages(lang);
      await i18n.changeLanguage(lang);
      render(<QueueTodoList todo={pinned(hint('free', [slot(1)]))} />);
      expect(screen.getByTestId('todo-slot-hint').textContent).toBe(expected);
    });
  });

  describe('a short spool (#3634)', () => {
    const lava = { type: 'PLA', color: '#C12E1F', color_name: 'Lava Red', no_stock: false };
    const shortEntry = (filament: Partial<QueueTodoEntry['filaments'][number]>, slot_hint: QueueTodoSlotHint | null): QueueTodo => ({
      count: 1,
      groups: [{
        printer_id: 1, printer_name: 'Farm-A1', target_model: null,
        entries: [{ kind: 'load_filament', jobs: [{ id: 1, name: 'Job', can_start: false }], filaments: [{ ...lava, short: true, ...filament }], printers: [], detail: null, slot_hint }],
      }],
    });
    const replace = (...slots: QueueTodoHintSlot[]) => hint('replace', slots);

    it('says how much the spool has and what the job needs', () => {
      render(<QueueTodoList todo={shortEntry(
        { short_trays: [{ ams_id: 0, tray_id: 1, remaining_grams: 12.4 }], required_grams: 30 },
        replace(slot(1, 'PLA', '#C12E1F', { remaining_grams: 12.4 })),
      )} />);
      expect(screen.getByTestId('todo-short')).toHaveTextContent('Not enough PLA Lava Red: A2 has 12 g, the job needs 30 g');
    });

    it('adds up the spools of a pool', () => {
      render(<QueueTodoList todo={shortEntry(
        { short_trays: [{ ams_id: 0, tray_id: 1, remaining_grams: 12 }, { ams_id: 0, tray_id: 2, remaining_grams: 13 }], required_grams: 60 },
        null,
      )} />);
      expect(screen.getByTestId('todo-short')).toHaveTextContent('Not enough PLA Lava Red: A2 + A3 have 25 g, the job needs 60 g');
    });

    it('leaves the grams out when they are not known', () => {
      render(<QueueTodoList todo={shortEntry({ short_trays: [{ ams_id: 0, tray_id: 1, remaining_grams: null }], required_grams: 30 }, null)} />);
      expect(screen.getByTestId('todo-short').textContent).toBe('Not enough PLA Lava Red in A2');
    });

    it('leaves out what the job needs when that is not known', () => {
      render(<QueueTodoList todo={shortEntry({ short_trays: [{ ams_id: 0, tray_id: 1, remaining_grams: 12 }], required_grams: null }, null)} />);
      expect(screen.getByTestId('todo-short').textContent).toBe('Not enough PLA Lava Red: A2 has 12\u00a0g');
    });

    it('keeps the number and its unit together and formats the number', () => {
      render(<QueueTodoList todo={shortEntry(
        { short_trays: [{ ams_id: 0, tray_id: 1, remaining_grams: 1234 }], required_grams: 2500 },
        null,
      )} />);
      expect(screen.getByTestId('todo-short').textContent).toBe(
        'Not enough PLA Lava Red: A2 has 1,234\u00a0g, the job needs 2,500\u00a0g',
      );
    });

    it('names no tray for an entry of an "Any <model>" group', () => {
      render(<QueueTodoList todo={shortEntry({ short_trays: [], required_grams: 30 }, null)} />);
      expect(screen.getByTestId('todo-short').textContent).toBe('Not enough PLA Lava Red');
    });

    it('labels an AMS-HT tray from its slot in the hint', () => {
      render(<QueueTodoList todo={shortEntry(
        { short_trays: [{ ams_id: 128, tray_id: 0, remaining_grams: 5 }], required_grams: 30 },
        replace(slot(0, 'PLA', '#C12E1F', { ams_id: 128, is_ht: true, ams_type: 4, remaining_grams: 5 })),
      )} />);
      expect(screen.getByTestId('todo-short').textContent).toContain('HT-A has 5\u00a0g');
    });

    it('shows the replace hint with what is left, or without when unknown', () => {
      const { unmount } = render(<QueueTodoList todo={shortEntry({}, replace(slot(1, 'PLA', '#C12E1F', { remaining_grams: 12 })))} />);
      expect(screen.getByTestId('todo-slot-hint').textContent).toMatch(/^Replace: A2 \(PLA .+, 12\u00a0g left\)$/);
      unmount();
      render(<QueueTodoList todo={shortEntry({}, replace(slot(1, 'PLA', '#C12E1F', { remaining_grams: null })))} />);
      expect(screen.getByTestId('todo-slot-hint').textContent).toMatch(/^Replace: A2 \(PLA [^,]+\)$/);
    });

    it('keeps a missing filament as it was', () => {
      render(<QueueTodoList todo={pinned(hint('free', [slot(1)]))} />);
      expect(screen.queryByTestId('todo-short')).toBeNull();
      expect(screen.getByText('PLA Pink')).toBeInTheDocument();
    });

    it('is translated: the German line', async () => {
      await i18n.loadLanguages('de');
      await i18n.changeLanguage('de');
      try {
        render(<QueueTodoList todo={shortEntry({ short_trays: [{ ams_id: 0, tray_id: 1, remaining_grams: 12 }], required_grams: 30 }, null)} />);
        expect(screen.getByTestId('todo-short').textContent).toBe('Nicht genug PLA Lava Red: A2 hat noch 12\u00a0g, der Auftrag braucht 30\u00a0g');
      } finally {
        await i18n.changeLanguage('en');
      }
    });
  });

  const anyEntry = (count: number): QueueTodo => {
    const ids = Array.from({ length: count }, (_, i) => i + 1);
    const entry: QueueTodoEntry = {
      kind: 'load_filament',
      jobs: [{ id: 9, name: 'Model job', can_start: false }],
      filaments: [pink],
      printers: ids.map((id) => ({ id, name: `Farm-X1C-${id}` })),
      detail: null,
      slot_hints: ids.map((id) => ({ printer_id: id, ...(id % 2 ? hint('free', [slot(id % 4)]) : hint('all_needed')) })),
    };
    return { count: 1, groups: [{ printer_id: null, printer_name: 'X1C', target_model: 'X1C', entries: [entry] }] };
  };

  it('lists an "Any" entry per printer, three first and the rest behind +N more', () => {
    render(<QueueTodoList todo={anyEntry(5)} />);
    const box = screen.getByTestId('todo-slot-hints');
    expect(box).toHaveTextContent('Farm-X1C-1: Free: A2');
    expect(box).toHaveTextContent('Farm-X1C-3: Free: A4');
    expect(box).not.toHaveTextContent('Farm-X1C-4');
    const toggle = screen.getByRole('button', { name: '+2 more' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(toggle);

    expect(box).toHaveTextContent('Farm-X1C-4: Every loaded filament is needed by a waiting job');
    expect(box).toHaveTextContent('Farm-X1C-5');
    const less = screen.getByRole('button', { name: 'Show fewer' });
    expect(less).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(less);
    expect(box).not.toHaveTextContent('Farm-X1C-4');
  });

  it('hangs the continuation lines of a printer under it', () => {
    const entry: QueueTodoEntry = {
      kind: 'load_filament',
      jobs: [{ id: 9, name: 'Model job', can_start: false }],
      filaments: [pink],
      printers: [{ id: 1, name: 'X1C-2' }, { id: 2, name: 'H2D-1' }],
      detail: null,
      slot_hints: [
        { printer_id: 1, ...hint('free', [slot(1)], { unknown_jobs: 2 }) },
        {
          printer_id: 2,
          ...hint('free', [slot(1, '', '', { nozzle: 'left' })], {
            by_nozzle: [
              { nozzle: 'left', state: 'free', slots: [slot(1, '', '', { nozzle: 'left' })] },
              { nozzle: 'right', state: 'all_needed', slots: [] },
            ],
          }),
        },
      ],
    };
    render(<QueueTodoList todo={{ count: 1, groups: [{ printer_id: null, printer_name: 'Any', target_model: 'X1C', entries: [entry] }] }} />);
    const [single, dual] = screen.getAllByTestId('todo-slot-hint-printer');
    // One main line, the unknown-jobs line indented under it.
    expect(Array.from(single.children).map((c) => [c.textContent, c.className.includes('pl-3')])).toEqual([
      ['X1C-2: Free: A2', false],
      ['2 waiting jobs have unknown filaments', true],
    ]);
    // A dual-nozzle printer: its name alone, the nozzles under it.
    expect(Array.from(dual.children).map((c) => [c.textContent, c.className.includes('pl-3')])).toEqual([
      ['H2D-1', false],
      ['Left nozzle: Free: A2', true],
      ['Right nozzle: Every loaded filament is needed by a waiting job', true],
    ]);
  });

  it('has no toggle for three printers or fewer', () => {
    render(<QueueTodoList todo={anyEntry(3)} />);
    expect(screen.getByTestId('todo-slot-hints')).toHaveTextContent('Farm-X1C-3');
    expect(screen.queryByRole('button', { name: /more|fewer/ })).toBeNull();
  });

  it('shows no hint on entries of another kind', () => {
    const t2 = pinned(hint('free', [slot(1)]));
    t2.groups[0].entries[0].kind = 'start_staged';
    render(<QueueTodoList todo={t2} />);
    expect(screen.queryByTestId('todo-slot-hint')).toBeNull();
  });
});

describe('QueueTodoList prepare lines (#3640)', () => {
  const slot = (tray_id: number, type = '', color = '', extra: Partial<QueueTodoHintSlot> = {}): QueueTodoHintSlot => ({
    ams_id: 0, tray_id, is_ht: false, is_external: false, ams_type: 1, nozzle: null, type, color, tray_info_idx: '', tray_sub_brands: '', ...extra,
  });
  const hint = (state: QueueTodoSlotHint['state'], slots: QueueTodoHintSlot[] = [], extra: Partial<QueueTodoSlotHint> = {}): QueueTodoSlotHint => ({
    state, slots, unknown_jobs: 0, by_nozzle: [], ...extra,
  });
  const petg = { type: 'PETG', color: '#000000', color_name: 'Black', no_stock: false };
  const plaBlue = { type: 'PLA', color: '#0000FF', color_name: 'Blue', no_stock: false };
  const line = (position: 1 | 2, name: string, extra: Partial<QueueTodoPrepare> = {}): QueueTodoPrepare => ({
    job: { id: position, name }, position, filaments: [petg, plaBlue], slot_hint: hint('free', [slot(2)]), ...extra,
  });
  const only = (prepare: QueueTodoPrepare[], entries: QueueTodoEntry[] = []): QueueTodo => ({
    count: entries.length,
    groups: [{ printer_id: 1, printer_name: 'Farm-X1C', target_model: null, entries, prepare }],
  });

  it('shows the next job, what it needs and where it can go', () => {
    render(<QueueTodoList todo={only([line(1, 'Bracket')])} />);
    const row = screen.getByTestId('todo-prepare-row');
    expect(screen.getByTestId('todo-prepare')).toHaveTextContent('Prepare');
    expect(row).toHaveTextContent('Next: Bracket needs PETG Black, PLA Blue');
    expect(screen.getByTestId('todo-prepare-hint')).toHaveTextContent('Free: A3');
  });

  it('labels by place in the list: a dropped first line leaves no lone "Then"', () => {
    const blank = { type: '', color: '', color_name: '', no_stock: false };
    render(<QueueTodoList todo={only([line(1, 'Bracket', { filaments: [blank] }), line(2, 'Lid')])} />);
    const rows = screen.getAllByTestId('todo-prepare-row');
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent('Next: Lid needs');
  });

  it('says "Then" for the second job, in order', () => {
    render(<QueueTodoList todo={only([line(1, 'Bracket'), line(2, 'Lid', { slot_hint: hint('all_needed') })])} />);
    const rows = screen.getAllByTestId('todo-prepare-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Next: Bracket');
    expect(rows[1]).toHaveTextContent('Then: Lid needs PETG Black, PLA Blue');
    expect(rows[1]).toHaveTextContent('Every loaded filament is needed by a waiting job');
  });

  it('shows the list for a printer that has prepare lines and nothing else to do', () => {
    render(<QueueTodoList todo={only([line(1, 'Bracket')])} />);
    expect(screen.getByTestId('queue-todo-list')).toBeInTheDocument();
    expect(screen.getByText('Farm-X1C')).toBeInTheDocument();
  });

  it('shows the lines under the entries of the same printer', () => {
    const entry: QueueTodoEntry = { kind: 'plate_clear', jobs: [{ id: 9, name: 'Now', can_start: false }], filaments: [], printers: [], detail: null };
    render(<QueueTodoList todo={only([line(1, 'Bracket')], [entry])} />);
    const entryEl = screen.getByTestId('todo-entry-plate_clear');
    const prepare = screen.getByTestId('todo-prepare');
    expect(entryEl.compareDocumentPosition(prepare) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('leaves out a group with neither entries nor prepare lines', () => {
    const entry: QueueTodoEntry = { kind: 'plate_clear', jobs: [{ id: 9, name: 'Now', can_start: false }], filaments: [], printers: [], detail: null };
    const mixed: QueueTodo = {
      count: 1,
      groups: [
        { printer_id: 1, printer_name: 'Farm-X1C', target_model: null, entries: [entry], prepare: [] },
        { printer_id: 2, printer_name: 'Farm-P1S', target_model: null, entries: [], prepare: [] },
      ],
    };
    const { container } = render(<QueueTodoList todo={mixed} />);
    expect(container.querySelectorAll('section')).toHaveLength(1);
    expect(screen.queryByText('Farm-P1S')).toBeNull();
  });

  it('is hidden when no group has anything to show', () => {
    const empty: QueueTodo = { count: 0, groups: [{ printer_id: 1, printer_name: 'Farm-X1C', target_model: null, entries: [], prepare: [] }] };
    const { container } = render(<QueueTodoList todo={empty} />);
    expect(container.querySelector('[data-testid="queue-todo-list"]')).toBeNull();
  });

  it('renders a group of prepare rows only without an empty entries list or a second rule', () => {
    const { container } = render(<QueueTodoList todo={only([line(1, 'Bracket')])} />);
    // The one list is the prepare list.
    expect(container.querySelectorAll('section ul')).toHaveLength(1);
    expect(screen.getByTestId('todo-prepare').className).not.toMatch(/border-t|mt-1/);
  });

  it('keeps the rule between entries and prepare rows', () => {
    const entry: QueueTodoEntry = { kind: 'plate_clear', jobs: [{ id: 9, name: 'Now', can_start: false }], filaments: [], printers: [], detail: null };
    render(<QueueTodoList todo={only([line(1, 'Bracket')], [entry])} />);
    expect(screen.getByTestId('todo-prepare').className).toMatch(/border-t/);
  });

  it('labels the prepare list with its heading', () => {
    render(<QueueTodoList todo={only([line(1, 'Bracket')])} />);
    const heading = screen.getByRole('heading', { level: 4, name: 'Prepare' });
    expect(screen.getByRole('list', { name: 'Prepare' })).toHaveAttribute('aria-labelledby', heading.id);
  });

  it('shows the hint in the plain gray of the other rows', () => {
    render(<QueueTodoList todo={only([line(1, 'Bracket')])} />);
    const hintEl = screen.getByTestId('todo-prepare-hint');
    expect(hintEl).toHaveClass('text-bambu-gray');
    expect(hintEl.className).not.toMatch(/gray-light/);
  });

  it('marks a filament that is out of stock, as a load entry does', () => {
    render(<QueueTodoList todo={only([line(1, 'Bracket', { filaments: [{ ...petg, no_stock: true }, plaBlue] })])} />);
    expect(screen.getByTestId('todo-prepare-row')).toHaveTextContent('Next: Bracket needs PETG Black (none left in inventory), PLA Blue');
  });

  it('names a filament without a colour name by its colour code, and never says "needs" alone', () => {
    const unnamed = { type: 'PETG', color: '#123456', color_name: '', no_stock: false };
    const blank = { type: '', color: '', color_name: '', no_stock: false };
    render(<QueueTodoList todo={only([line(1, 'Bracket', { filaments: [unnamed, blank] }), line(2, 'Lid', { filaments: [blank] })])} />);
    const rows = screen.getAllByTestId('todo-prepare-row');
    // The line that lists nothing is left out.
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent('Next: Bracket needs PETG #123456');
    expect(rows[0].textContent).not.toMatch(/needs\s*$/);
  });

  it('works against a server that sends no prepare list', () => {
    const entry: QueueTodoEntry = { kind: 'plate_clear', jobs: [{ id: 9, name: 'Now', can_start: false }], filaments: [], printers: [], detail: null };
    render(<QueueTodoList todo={{ count: 1, groups: [{ printer_id: 1, printer_name: 'Farm-X1C', target_model: null, entries: [entry] }] }} />);
    expect(screen.queryByTestId('todo-prepare')).toBeNull();
  });

  it('shows no hint line without a hint', () => {
    render(<QueueTodoList todo={only([line(1, 'Bracket', { slot_hint: null })])} />);
    expect(screen.queryByTestId('todo-prepare-hint')).toBeNull();
  });

  it('prefixes the nozzle on a dual-nozzle printer and names the nozzle a filament wants', () => {
    const left = { ...petg, nozzle: 1 };
    const parts = [
      { nozzle: 'right' as const, state: 'all_needed' as const, slots: [] },
      { nozzle: 'left' as const, state: 'free' as const, slots: [slot(1, '', '', { nozzle: 'left' })] },
    ];
    render(<QueueTodoList todo={only([line(1, 'Bracket', { filaments: [left], slot_hint: hint('free', parts[1].slots, { by_nozzle: parts }) })])} />);
    expect(screen.getByTestId('todo-prepare-row')).toHaveTextContent('Next: Bracket needs PETG Black (Left nozzle)');
    expect(screen.getByTestId('todo-prepare-hint')).toHaveTextContent('Left nozzle: Free: A2');
  });

  it('counts the jobs with unknown filaments', () => {
    render(<QueueTodoList todo={only([line(1, 'Bracket', { slot_hint: hint('free', [slot(1)], { unknown_jobs: 2 }) })])} />);
    expect(screen.getByTestId('todo-prepare-hint')).toHaveTextContent('2 waiting jobs have unknown filaments');
  });

  it('keeps a job name with markup as text', () => {
    render(<QueueTodoList todo={only([line(1, '<b>Bold</b> & co')])} />);
    expect(screen.getByTestId('todo-prepare-row')).toHaveTextContent('Next: <b>Bold</b> & co needs');
    expect(screen.getByTestId('todo-prepare-row').querySelector('b')).toBeNull();
  });

  it('is translated', async () => {
    await i18n.loadLanguages('de');
    await i18n.changeLanguage('de');
    try {
      render(<QueueTodoList todo={only([line(1, 'Bracket'), line(2, 'Lid')])} />);
      const rows = screen.getAllByTestId('todo-prepare-row');
      expect(rows[0]).toHaveTextContent('Als Nächstes: Bracket braucht PETG Black, PLA Blue');
      expect(rows[1]).toHaveTextContent('Danach: Lid braucht');
    } finally {
      await i18n.changeLanguage('en');
    }
  });

  it('is not counted: the badge shows what the queue waits on, not the prepare lines', async () => {
    const entry: QueueTodoEntry = { kind: 'plate_clear', jobs: [{ id: 9, name: 'Now', can_start: false }], filaments: [], printers: [], detail: null };
    const served: QueueTodo = {
      count: 1,
      groups: [
        { printer_id: 1, printer_name: 'Farm-X1C', target_model: null, entries: [entry], prepare: [line(1, 'Bracket'), line(2, 'Lid')] },
        { printer_id: 2, printer_name: 'Farm-P1S', target_model: null, entries: [], prepare: [line(1, 'Cover')] },
      ],
    };
    const hit = vi.fn();
    server.use(
      http.get('/api/v1/queue/todo', () => {
        hit();
        return HttpResponse.json(served);
      }),
    );
    render(<QueueTodoLauncher />);
    await waitFor(() => expect(hit).toHaveBeenCalled());
    expect(await screen.findByTestId('queue-todo-badge')).toHaveTextContent(/^1$/);
  });

  it('shows no badge when only prepare lines are served', async () => {
    const hit = vi.fn();
    server.use(
      http.get('/api/v1/queue/todo', () => {
        hit();
        return HttpResponse.json(only([line(1, 'Bracket')]));
      }),
    );
    render(<QueueTodoLauncher />);
    await waitFor(() => expect(hit).toHaveBeenCalled());
    expect(screen.queryByTestId('queue-todo-badge')).toBeNull();
  });
});

describe('QueueTodoLauncher', () => {
  it('shows the entry count and opens the panel', async () => {
    server.use(http.get('/api/v1/queue/todo', () => HttpResponse.json(todo)));
    render(<QueueTodoLauncher />);
    const badge = await screen.findByTestId('queue-todo-badge');
    expect(badge).toHaveTextContent('6');
    fireEvent.click(badge);
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();
  });

  it('anchors beside the rail or the open sidebar on a wide screen', async () => {
    server.use(http.get('/api/v1/queue/todo', () => HttpResponse.json(todo)));
    const prev = window.innerWidth;
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 1600 });
    try {
      for (const [expanded, cls] of [[false, 'md:left-[5rem]'], [true, 'md:left-[17rem]']] as const) {
        const { unmount } = render(<QueueTodoLauncher sidebarExpanded={expanded} />);
        fireEvent.click(await screen.findByTestId('queue-todo-badge'));
        expect(await screen.findByRole('dialog')).toHaveClass(cls);
        unmount();
      }
    } finally {
      Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: prev });
    }
  });

  it('renders no badge when the list is empty', async () => {
    const hit = vi.fn();
    server.use(
      http.get('/api/v1/queue/todo', () => {
        hit();
        return HttpResponse.json({ count: 0, groups: [] });
      }),
    );
    render(<QueueTodoLauncher />);
    await waitFor(() => expect(hit).toHaveBeenCalled());
    expect(screen.queryByTestId('queue-todo-badge')).toBeNull();
  });
});

function withClient(ui: React.ReactElement, client: QueryClient) {
  return rtlRender(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>{ui}</ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('QueueTodoLauncher panel behaviour', () => {
  it('is an accessible modal dialog in document.body with focus handling', async () => {
    server.use(http.get('/api/v1/queue/todo', () => HttpResponse.json(todo)));
    const { container } = render(<QueueTodoLauncher />);
    const trigger = (await screen.findByTestId('queue-todo-badge')).closest('button') as HTMLButtonElement;
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(trigger);
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(container.contains(dialog)).toBe(false);
    expect(document.body.contains(dialog)).toBe(true);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(trigger).toHaveFocus();
  });

  it('does not reopen by itself after the list emptied and filled again', async () => {
    let body: QueueTodo = todo;
    server.use(http.get('/api/v1/queue/todo', () => HttpResponse.json(body)));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    withClient(<QueueTodoLauncher />, client);
    fireEvent.click(await screen.findByTestId('queue-todo-badge'));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    body = { count: 0, groups: [] };
    await client.invalidateQueries({ queryKey: ['queue-todo'] });
    await waitFor(() => expect(screen.queryByTestId('queue-todo-badge')).toBeNull());
    body = todo;
    await client.invalidateQueries({ queryKey: ['queue-todo'] });
    await screen.findByTestId('queue-todo-badge');
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('useQueueTodoAutoRefresh debounce', () => {
  it('coalesces a burst into one refetch and ignores per-printer card queries', async () => {
    vi.useFakeTimers();
    try {
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const spy = vi.spyOn(client, 'invalidateQueries');
      renderHook(() => useQueueTodoAutoRefresh(), {
        wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
      });
      await client.fetchQuery({ queryKey: ['queue', 3, 'pending'], queryFn: async () => [] });
      await client.fetchQuery({ queryKey: ['queue', 3, 'pending', 'X1C'], queryFn: async () => [] });
      await vi.advanceTimersByTimeAsync(3000);
      expect(spy).not.toHaveBeenCalled();
      await client.fetchQuery({ queryKey: ['queue', 'pending'], queryFn: async () => [] });
      await client.fetchQuery({ queryKey: ['queue', null, 'pending,printing,skipped'], queryFn: async () => [] });
      await client.fetchQuery({ queryKey: ['queue', 'history', {}, 'x', false, 10], queryFn: async () => [] });
      expect(spy).not.toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(1600);
      expect(spy).toHaveBeenCalledTimes(1);
      expect(spy).toHaveBeenCalledWith({ queryKey: ['queue-todo'] });
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('useQueueTodoAutoRefresh', () => {
  it('invalidates the to-do list when a queue query refetches, not for others', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(client, 'invalidateQueries');
    renderHook(() => useQueueTodoAutoRefresh(), {
      wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
    });
    await client.fetchQuery({ queryKey: ['printers'], queryFn: async () => [] });
    expect(spy).not.toHaveBeenCalled();
    await client.fetchQuery({ queryKey: ['queue', 'pending'], queryFn: async () => [] });
    await waitFor(() => expect(spy).toHaveBeenCalledWith({ queryKey: ['queue-todo'] }), { timeout: 3000 });
  });
});

describe('QueueTodoList paused prints (#3648)', () => {
  const slot = (over: Partial<QueueTodoPausedSlot> = {}): QueueTodoPausedSlot => ({
    ams_id: 0,
    tray_id: 0,
    is_ht: false,
    is_external: false,
    ams_type: 0,
    type: 'PLA',
    color: '#C12E1F',
    tray_info_idx: 'GFA00',
    tray_sub_brands: '',
    ...over,
  });
  const paused = (over: Partial<QueueTodoPaused> = {}): QueueTodoPaused => ({
    job_name: 'Benchy',
    progress: 42,
    remaining_minutes: 95,
    cause: 'paused',
    ran_out: null,
    expected: null,
    error: null,
    more_errors: 0,
    ...over,
  });
  const renderPaused = (info: QueueTodoPaused, jobs: { id: number; name: string; can_start: boolean }[] = []) =>
    render(
      <QueueTodoList
        todo={{
          count: 1,
          groups: [{
            printer_id: 1,
            printer_name: 'Alpha',
            target_model: null,
            entries: [{ kind: 'print_paused', jobs, filaments: [], printers: [], detail: null, paused: info }],
          }],
        }}
      />,
    );
  const filament = `PLA ${getColorName('#C12E1F', null, 'GFA00')}`;

  it('names the slot that ran out, the slot to refill and the filament', () => {
    renderPaused(paused({ cause: 'runout_ams', ran_out: slot(), expected: slot({ tray_id: 1, type: '', color: '' }) }));
    const row = screen.getByTestId('todo-entry-print_paused');
    expect(row).toHaveTextContent('Print paused');
    expect(screen.getByTestId('todo-paused-progress')).toHaveTextContent('Benchy · 42% · 1h 35m left');
    expect(screen.getByTestId('todo-paused-cause')).toHaveTextContent(
      `Filament ran out in A1. Load ${filament} into A2, then resume.`,
    );
  });

  it('names only the slot to refill when the one that ran out is unknown', () => {
    renderPaused(paused({ cause: 'runout_ams', expected: slot({ tray_id: 2, ams_id: 128, is_ht: true, ams_type: 1 }) }));
    expect(screen.getByTestId('todo-paused-cause')).toHaveTextContent(`Load ${filament} into HT-A, then resume.`);
  });

  it('asks to check the printer when no slot can be told', () => {
    renderPaused(paused({ cause: 'runout_ams' }));
    expect(screen.getByTestId('todo-paused-cause')).toHaveTextContent(
      'Filament ran out. Check the printer screen for the slot it expects.',
    );
  });

  it('says to load a new spool on an external runout', () => {
    renderPaused(paused({ cause: 'runout_external' }));
    expect(screen.getByTestId('todo-paused-cause')).toHaveTextContent(
      'Filament ran out on the external spool. Load a new spool, then resume.',
    );
  });

  it('shows the error and how many more there are', () => {
    renderPaused(paused({ cause: 'error', error: { code: '0500-0100-0001-0006', description: 'The door is open' }, more_errors: 1 }));
    expect(screen.getByTestId('todo-paused-cause')).toHaveTextContent('The door is open (+1 more)');
  });

  it('shows the code of an error without text', () => {
    renderPaused(paused({ cause: 'error', error: { code: '0300-4001', description: null } }));
    expect(screen.getByTestId('todo-paused-cause')).toHaveTextContent('Error 0300-4001');
  });

  it('gives no reason line for a plain pause', () => {
    renderPaused(paused());
    expect(screen.queryByTestId('todo-paused-cause')).toBeNull();
    expect(screen.getByTestId('todo-paused-progress')).toBeInTheDocument();
  });

  it('leaves out the file and the parts the printer did not report', () => {
    renderPaused(paused({ job_name: null, remaining_minutes: null }));
    expect(screen.getByTestId('todo-paused-progress').textContent).toBe('42%');
    expect(screen.getByTestId('todo-entry-print_paused')).not.toHaveTextContent('Benchy');
  });

  it('has no progress line when nothing is known and does not repeat the waiting jobs', () => {
    renderPaused(paused({ job_name: null, progress: null, remaining_minutes: null }), [{ id: 9, name: 'Next up', can_start: false }]);
    expect(screen.queryByTestId('todo-paused-progress')).toBeNull();
    expect(screen.getByTestId('todo-entry-print_paused')).not.toHaveTextContent('Next up');
  });

  it('wraps long text instead of widening the panel', () => {
    renderPaused(paused({ job_name: 'A'.repeat(120), cause: 'error', error: { code: 'x', description: 'B'.repeat(200) } }));
    expect(screen.getByTestId('todo-paused-progress').className).toContain('break-words');
    expect(screen.getByTestId('todo-paused-cause').className).toContain('break-words');
    expect(screen.getByTestId('todo-entry-print_paused').querySelector('.min-w-0')).not.toBeNull();
  });
});
