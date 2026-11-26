/**
 * An "Any <model>" entry of the To do list draws exactly one AMS picture: the
 * one of the printer shown. Switching the printer, or a refetch that brings
 * another set of pictures, never leaves an earlier picture behind, and a
 * printer the list names twice is drawn and offered once.
 */
import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent, within } from '@testing-library/react';
import { render } from '../utils';
import type { QueueTodo, QueueTodoEntry, QueueTodoFilament, QueueTodoPicture, QueueTodoPictureSlot } from '../../api/client';

vi.mock('../../contexts/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../contexts/AuthContext')>();
  return {
    ...actual,
    useAuth: () => ({
      user: { id: 1, username: 'op', permissions: [] },
      authEnabled: true,
      loading: false,
      isAdmin: false,
      hasPermission: () => true,
      hasAnyPermission: () => true,
      canModify: () => true,
    }),
  };
});

import { QueueTodoList } from '../../components/QueueTodoList';

const cottonWhite: QueueTodoFilament = {
  type: 'PLA', color: '#E6DDDB', color_name: 'Cotton White', no_stock: false, short: true, required_grams: 21, short_trays: [],
};
const armyRed: QueueTodoFilament = { type: 'PLA', color: '#7B2D34', color_name: 'Army Red', no_stock: false };

function slot(trayId: number, colorName: string, color: string, more: Partial<QueueTodoPictureSlot> = {}): QueueTodoPictureSlot {
  return {
    ams_id: 0, tray_id: trayId, is_ht: false, is_external: false, ams_type: 2, type: 'PLA', color,
    extra_colors: '', effect_type: '', subtype: '', color_name: colorName, tray_sub_brands: '', tray_info_idx: '',
    remaining_g: 100, remain_percent: null, rfid: false, state: 'keep', incoming: null,
    ...more,
  };
}

// The AMS of the idle printer: Cotton White in A3 is too little, the external holder is folded away.
function pictureOf(printerId: number, printerName: string, filaments: QueueTodoFilament[]): QueueTodoPicture {
  const short = filaments[0].short;
  return {
    printer_id: printerId,
    printer_name: printerName,
    compact: false,
    unplaced: [],
    filaments,
    units: [
      {
        ams_id: 0, ams_type: 2, kind: 'ams_lite', nozzle: null, collapsed: false,
        slots: [
          slot(0, 'Charcoal Black', '#000000', { remaining_g: 323 }),
          slot(1, 'Army Beige', '#B2A78E', { remaining_g: 129 }),
          slot(2, 'Cotton White', '#E6DDDB', {
            remaining_g: 0,
            state: 'out',
            incoming: { filament_index: 0, type: 'PLA', color: filaments[0].color, color_name: filaments[0].color_name, required_g: short ? 21 : null, stock_count: 1 },
          }),
          slot(3, 'Army Red', '#7B2D34', { remaining_g: null, remain_percent: 100 }),
        ],
      },
      {
        ams_id: 255, ams_type: null, kind: 'external', nozzle: null, collapsed: true,
        slots: [slot(0, '', '', { ams_id: 255, is_external: true, ams_type: null, type: '', state: 'empty', remaining_g: null })],
      },
    ],
  };
}

const links = pictureOf(1, 'A1 Links', [cottonWhite]);
const rechts = pictureOf(2, 'A1 rechts', [armyRed]);

type Job = QueueTodoEntry['jobs'][number];
// Held on A1 Links only because Cotton White is short: Print anyway is offered there.
const job: Job = { id: 92, name: 'Lamp', can_start: true, short_only: false, short_only_printer_ids: [1] };

function todoWith(pictures: QueueTodoPicture[]): QueueTodo {
  return {
    count: 1,
    groups: [{
      printer_id: null,
      printer_name: 'A1',
      target_model: 'A1',
      entries: [{
        kind: 'load_filament',
        jobs: [job],
        filaments: [cottonWhite],
        printers: [{ id: 1, name: 'A1 Links' }],
        detail: null,
        priority: 'priority_in',
        priority_hours: 72,
        plate_capacity: null,
        ams_pictures: pictures,
      }],
      prepare: [],
    }],
  };
}

const entryRow = () => screen.getByTestId('todo-entry-load_filament');
const pictureCount = () => within(entryRow()).queryAllByTestId('todo-ams-picture').length;
const switchNames = () => within(entryRow()).queryAllByTestId('todo-ams-printer').map((b) => b.textContent);

describe('one AMS picture per To do entry', () => {
  it('still draws one picture after switching between the printers many times', () => {
    render(<QueueTodoList todo={todoWith([links, rechts])} />);
    expect(pictureCount()).toBe(1);
    for (let i = 0; i < 10; i += 1) {
      fireEvent.click(screen.getByRole('button', { name: /A1 rechts/ }));
      expect(pictureCount()).toBe(1);
      expect(within(entryRow()).queryAllByTestId('todo-print-anyway')).toHaveLength(0);
      fireEvent.click(screen.getByRole('button', { name: /A1 Links/ }));
      expect(pictureCount()).toBe(1);
      expect(within(entryRow()).getAllByTestId('todo-print-anyway')).toHaveLength(1);
    }
    expect(within(entryRow()).getAllByTestId('todo-ams-unit')).toHaveLength(1);
    expect(within(entryRow()).getAllByTestId('todo-ams-slot')).toHaveLength(4);
    expect(within(entryRow()).getAllByTestId('todo-slot-menu-hint')).toHaveLength(1);
  });

  it('still draws one picture when refetches bring the other printer and take it away again', () => {
    const { rerender } = render(<QueueTodoList todo={todoWith([links, rechts])} />);
    for (let i = 0; i < 10; i += 1) {
      rerender(<QueueTodoList todo={todoWith([pictureOf(1, 'A1 Links', [cottonWhite])])} />);
      expect(pictureCount()).toBe(1);
      rerender(<QueueTodoList todo={todoWith([pictureOf(1, 'A1 Links', [cottonWhite]), pictureOf(2, 'A1 rechts', [armyRed])])} />);
      expect(pictureCount()).toBe(1);
    }
    expect(within(entryRow()).getAllByTestId('todo-ams-slot')).toHaveLength(4);
    expect(within(entryRow()).getAllByTestId('todo-slot-menu-hint')).toHaveLength(1);
    expect(within(entryRow()).getAllByTestId('todo-print-anyway')).toHaveLength(1);
  });

  it('still draws one picture when a refetch changes which printer leads', () => {
    const { rerender } = render(<QueueTodoList todo={todoWith([links, rechts])} />);
    for (let i = 0; i < 10; i += 1) {
      rerender(<QueueTodoList todo={todoWith([rechts, links])} />);
      expect(pictureCount()).toBe(1);
      rerender(<QueueTodoList todo={todoWith([links, rechts])} />);
      expect(pictureCount()).toBe(1);
    }
  });

  it('draws and offers a printer once when the list names it several times', () => {
    const again = pictureOf(1, 'A1 Links', [armyRed]);
    render(<QueueTodoList todo={todoWith([links, again, rechts, again, rechts])} />);
    expect(pictureCount()).toBe(1);
    expect(switchNames()).toEqual([expect.stringContaining('A1 Links'), 'A1 rechts']);
    // The first picture of a printer is the one drawn.
    expect(within(entryRow()).getAllByTestId('todo-filament').map((li) => li.textContent)).toEqual([
      expect.stringContaining('Cotton White'),
    ]);
    fireEvent.click(screen.getByRole('button', { name: /A1 rechts/ }));
    expect(pictureCount()).toBe(1);
    expect(switchNames()).toHaveLength(2);
  });
});
