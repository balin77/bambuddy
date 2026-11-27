/**
 * A paused print whose filament ran out shows where the new spool goes and
 * which filament it is (#3648, #3726): the printer's AMS picture with every
 * slot that ran out marked, the filament the print needs above it, in one
 * picture, with Resume, Stop and Open printer kept as they are.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within, render as rtlRender } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '../../contexts/ToastContext';
import type { QueueTodo, QueueTodoEntry, QueueTodoFilament, QueueTodoPicture, QueueTodoPictureSlot } from '../../api/client';

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

import { QueueTodoList } from '../../components/QueueTodoList';

const pink: QueueTodoFilament = { type: 'PLA', color: '#F5A9B8', color_name: '', no_stock: false };
const black: QueueTodoFilament = { type: 'PLA', color: '#000000', color_name: 'Charcoal Black', no_stock: false };

function slot(trayId: number, more: Partial<QueueTodoPictureSlot> = {}): QueueTodoPictureSlot {
  return {
    ams_id: 0, tray_id: trayId, is_ht: false, is_external: false, ams_type: 2, type: 'PLA', color: '#FFFFFF',
    extra_colors: '', effect_type: '', subtype: '', color_name: '', tray_sub_brands: '', tray_info_idx: '',
    remaining_g: null, remain_percent: null, rfid: false, state: 'keep', incoming: null,
    ...more,
  };
}

// An A1 with its AMS Lite: A4 and A2 ran out, the external holder folded away.
function picture(): QueueTodoPicture {
  return {
    printer_id: 3,
    printer_name: 'A1 rechts',
    compact: false,
    unplaced: [],
    units: [
      {
        ams_id: 0, ams_type: 2, kind: 'ams_lite', nozzle: null, collapsed: false,
        slots: [
          slot(0),
          slot(1, {
            state: 'ran_out', type: '', color: '',
            incoming: { filament_index: 1, type: 'PLA', color: '#000000', color_name: 'Charcoal Black', required_g: null, stock_count: 0 },
          }),
          slot(2, { type: 'PETG', color: '#00FF00' }),
          slot(3, {
            state: 'ran_out', type: '', color: '',
            incoming: { filament_index: 0, type: 'PLA', color: '#F5A9B8', color_name: '', required_g: null, stock_count: 2 },
          }),
        ],
      },
      {
        ams_id: 255, ams_type: null, kind: 'external', nozzle: null, collapsed: true,
        slots: [slot(0, { ams_id: 255, is_external: true, ams_type: null, type: '', color: '', state: 'empty' })],
      },
    ],
  };
}

function pausedEntry(withPicture: boolean): QueueTodoEntry {
  return {
    kind: 'print_paused',
    jobs: [],
    filaments: [],
    printers: [],
    detail: null,
    priority: null,
    priority_hours: null,
    plate_capacity: null,
    paused: {
      job_name: 'hello_kitty.4x.A1.swap.jobox',
      progress: 15,
      remaining_minutes: 838,
      cause: 'runout_ams',
      ran_out: null,
      expected: null,
      error: null,
      more_errors: 0,
      ams_picture: withPicture ? picture() : null,
      filaments: withPicture ? [pink, black] : [],
    },
  };
}

function renderList(entry: QueueTodoEntry) {
  const todo: QueueTodo = {
    count: 1,
    groups: [{ printer_id: 3, printer_name: 'A1 rechts', target_model: null, prepare: [], entries: [entry] }],
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <QueueTodoList todo={todo} overlayZIndex="z-[70]" />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const row = () => screen.getByTestId('todo-entry-print_paused');

beforeEach(() => {
  perms.granted = new Set(['printers:pause_resume', 'printers:stop']);
  perms.hide = false;
});

describe('the picture of a paused print that ran out', () => {
  it('draws one picture with both slots that ran out', () => {
    renderList(pausedEntry(true));
    expect(within(row()).getAllByTestId('todo-ams-picture')).toHaveLength(1);
    const ranOut = within(row()).getAllByTestId('todo-ams-slot').filter((s) => s.dataset.state === 'ran_out');
    expect(ranOut.map((s) => s.textContent)).toEqual([expect.stringContaining('A2'), expect.stringContaining('A4')]);
    for (const s of ranOut) expect(s.textContent).toContain('ran out');
    // The external holder nothing goes into stays folded.
    expect(within(row()).getAllByTestId('todo-ams-unit')).toHaveLength(1);
  });

  it('puts the filament the print needs above the slot it goes into', () => {
    renderList(pausedEntry(true));
    const grid = within(row()).getByTestId('todo-ams-grid');
    const cards = within(grid).getAllByTestId('todo-ams-incoming');
    expect(cards).toHaveLength(2);
    // Column of each card: the column of its slot (A2 is column 2, A4 column 4).
    const byColumn = Object.fromEntries(cards.map((c) => [c.style.gridColumn, c]));
    expect(byColumn['2'].textContent).toContain('PLA Charcoal Black');
    expect(byColumn['2'].textContent).toContain('not in stock');
    expect(byColumn['4'].textContent).toContain('in stock: 2 spools');
    // A colour the file did not name is named as the printer card names it.
    expect(byColumn['4'].querySelector('div[title]')?.getAttribute('title')).toMatch(/^PLA \S+/);
    expect(within(grid).getAllByTestId('todo-ams-arrow').map((a) => a.style.gridColumn)).toEqual(['2', '4']);
  });

  it('names the slots in the cause line, short enough for a phone', () => {
    renderList(pausedEntry(true));
    expect(within(row()).getByTestId('todo-paused-cause').textContent).toBe(
      'Filament ran out in A2, A4. Load the filament shown, then resume.',
    );
    expect(within(row()).getByTestId('todo-paused-progress').textContent).toContain('hello_kitty.4x.A1.swap.jobox');
  });

  it('keeps Resume, Stop and Open printer', () => {
    renderList(pausedEntry(true));
    expect(within(row()).getByRole('button', { name: 'Resume' })).toBeEnabled();
    expect(within(row()).getByRole('button', { name: 'Stop' })).toBeEnabled();
    expect(within(row()).getByRole('link', { name: 'Open printer' })).toHaveAttribute('href', '/printers#printer-card-3');
  });

  it('draws the picture for who may not resume or stop, without the buttons when they are hidden', () => {
    perms.granted = new Set();
    perms.hide = true;
    renderList(pausedEntry(true));
    expect(within(row()).getAllByTestId('todo-ams-picture')).toHaveLength(1);
    expect(screen.queryByTestId('todo-paused-actions')).toBeNull();
    expect(within(row()).getByRole('link', { name: 'Open printer' })).toBeInTheDocument();
  });

  it('greys the buttons out for who may not use them when nothing is hidden', () => {
    perms.granted = new Set();
    renderList(pausedEntry(true));
    expect(within(row()).getByRole('button', { name: 'Resume' })).toBeDisabled();
    expect(within(row()).getByRole('button', { name: 'Stop' })).toBeDisabled();
  });

  it('is left out, with the sentence as before, when the list has no picture', () => {
    renderList(pausedEntry(false));
    expect(within(row()).queryByTestId('todo-ams-picture')).toBeNull();
    expect(within(row()).getByTestId('todo-paused-cause').textContent).toBe(
      'Filament ran out. Check the printer screen for the slot it expects.',
    );
  });
});
