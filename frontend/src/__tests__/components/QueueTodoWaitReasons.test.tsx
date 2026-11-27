/**
 * The "To do" list names a short spool's slot as the printer card does (#3615).
 * Farm takes only the test of upstream's 874a703ad here; the earlier wait
 * reasons are covered by farm's own To do tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { render } from '../utils';
import type { QueueTodo, QueueTodoEntry, QueueTodoFilament } from '../../api/client';

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

const job = { id: 10, name: 'Benchy', can_start: false };

function entry(partial: Partial<QueueTodoEntry> & Pick<QueueTodoEntry, 'kind'>): QueueTodoEntry {
  return { jobs: [job], filaments: [], printers: [], detail: null, ...partial };
}

function onPrinter(...entries: QueueTodoEntry[]): QueueTodo {
  return {
    count: entries.length,
    groups: [{ printer_id: 1, printer_name: 'Alpha', target_model: null, entries }],
  };
}

function filament(partial: Partial<QueueTodoFilament>): QueueTodoFilament {
  return { type: 'PLA', color: '#FF0000', color_name: 'Red', no_stock: false, ...partial };
}

beforeEach(() => {
  perms.granted = new Set(['printers:clear_plate', 'queue:update_all', 'queue:read_all']);
});

describe('a spool that holds too little', () => {
  const short = (partial: Partial<QueueTodoFilament> = {}) =>
    filament({
      short: true,
      short_trays: [{ ams_id: 0, tray_id: 1, remaining_grams: 20.4 }],
      required_grams: 299.6,
      ...partial,
    });

  it('names an external input of a rack printer by the PrintTool it feeds', () => {
    const todo = onPrinter(
      entry({
        kind: 'load_filament',
        filaments: [short({ short_trays: [{ ams_id: 255, tray_id: 4, remaining_grams: 7 }] })],
      }),
    );
    todo.groups[0].printer_model = 'H3C';
    render(<QueueTodoList todo={todo} />);
    expect(screen.getByTestId('todo-short')).toHaveTextContent('Not enough PLA Red: Ext-7 has 7 g');
  });
});
