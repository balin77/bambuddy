/**
 * "Print anyway" in the To do list is offered per printer: an "Any <model>"
 * job whose spool is too short on one printer and missing on the others gets
 * the button under the short printer, and is started on exactly that printer.
 */
import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import type { QueueTodo, QueueTodoEntry, QueueTodoFilament, QueueTodoPicture } from '../../api/client';

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

const lavaRed: QueueTodoFilament = {
  type: 'PLA', color: '#C8102E', color_name: 'Lava Red', no_stock: false, short: true, required_grams: 505, short_trays: [],
};

function pictureOf(printerId: number, printerName: string): QueueTodoPicture {
  return {
    printer_id: printerId,
    printer_name: printerName,
    compact: false,
    unplaced: [],
    units: [{
      ams_id: 0, ams_type: 1, kind: 'ams', nozzle: null, collapsed: false,
      slots: [{
        ams_id: 0, tray_id: 2, is_ht: false, is_external: false, ams_type: 1, type: 'PLA', color: '#C8102E',
        extra_colors: '', effect_type: '', subtype: '', color_name: 'Lava Red', tray_sub_brands: '', tray_info_idx: '',
        remaining_g: 196, remain_percent: null, rfid: true, state: 'out',
        incoming: { filament_index: 0, type: 'PLA', color: '#C8102E', color_name: 'Lava Red', required_g: 505, stock_count: null },
      }],
    }],
  };
}

const left = { id: 1, name: 'P1S left' };
const right = { id: 2, name: 'P1S right' };

type Job = QueueTodoEntry['jobs'][number];

// An "Any P1S" entry: the jobs, the printers it lists and the pictures it draws.
function modelEntry(jobs: Job[], printers: { id: number; name: string }[], withPictures = true): QueueTodo {
  return {
    count: 1,
    groups: [{
      printer_id: null,
      printer_name: 'P1S',
      target_model: 'P1S',
      entries: [{
        kind: 'load_filament',
        jobs,
        filaments: [lavaRed],
        printers,
        detail: null,
        priority: null,
        priority_hours: null,
        plate_capacity: null,
        ams_pictures: withPictures ? printers.map((p) => pictureOf(p.id, p.name)) : [],
      }],
      prepare: [],
    }],
  };
}

// The job of the report: short on the left printer, the colour missing on the others.
const shortOnLeft: Job = { id: 30, name: 'Lamp', can_start: true, short_only: false, short_only_printer_ids: [1] };

function recordStarts(itemId: number): string[] {
  const calls: string[] = [];
  server.use(
    http.post(`/api/v1/queue/${itemId}/start`, ({ request }) => {
      const url = new URL(request.url);
      calls.push(url.search);
      if (url.searchParams.get('skip_filament_check')) return HttpResponse.json({ id: itemId });
      return HttpResponse.json(
        { detail: { code: 'insufficient_filament', message: 'short', deficit: [{ slot_id: 1, required_grams: 505, remaining_grams: 196, printer_name: 'P1S left' }] } },
        { status: 409 },
      );
    }),
  );
  return calls;
}

describe('Print anyway per printer in the To do list', () => {
  it('offers it under the printer whose spool is short, although the job misses the colour elsewhere', () => {
    render(<QueueTodoList todo={modelEntry([shortOnLeft], [left])} />);
    expect(screen.getByTestId('todo-ams-picture')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Print Anyway' })).toHaveAttribute('data-testid', 'todo-print-anyway');
  });

  it('asks the shortage question and starts the job on the printer shown', async () => {
    const calls = recordStarts(30);
    render(<QueueTodoList todo={modelEntry([shortOnLeft], [left])} />);
    fireEvent.click(screen.getByTestId('todo-print-anyway'));
    expect(await screen.findByText(/P1S left: /)).toBeInTheDocument();
    expect(screen.getByText('Insufficient filament')).toBeInTheDocument();
    // Nothing is started before the answer.
    expect(calls).toEqual(['?printer_id=1']);
    fireEvent.click(screen.getAllByRole('button', { name: 'Print Anyway' }).find((b) => !b.hasAttribute('data-testid'))!);
    await waitFor(() => expect(calls).toEqual(['?printer_id=1', '?skip_filament_check=true&printer_id=1']));
  });

  it('follows the printer shown: there on the short one, gone on one that lacks the filament', () => {
    render(<QueueTodoList todo={modelEntry([shortOnLeft], [left, right])} />);
    expect(screen.getAllByTestId('todo-print-anyway')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: /P1S right/ }));
    expect(screen.queryByTestId('todo-print-anyway')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /P1S left/ }));
    expect(screen.getAllByTestId('todo-print-anyway')).toHaveLength(1);
  });

  it('starts on the printer switched to', async () => {
    const calls = recordStarts(30);
    const both: Job = { ...shortOnLeft, short_only: true, short_only_printer_ids: [1, 2] };
    render(<QueueTodoList todo={modelEntry([both], [left, right])} />);
    fireEvent.click(screen.getByRole('button', { name: /P1S right/ }));
    fireEvent.click(screen.getByTestId('todo-print-anyway'));
    await waitFor(() => expect(calls).toEqual(['?printer_id=2']));
  });

  it('has one button per startable job of the printer shown, named when several wait', () => {
    render(<QueueTodoList todo={modelEntry([
      shortOnLeft,
      { ...shortOnLeft, id: 31, name: 'Cube' },
      { ...shortOnLeft, id: 32, name: 'Not mine', can_start: false },
      { ...shortOnLeft, id: 33, name: 'Staged', short_only_printer_ids: [] },
    ], [left])} />);
    expect(screen.getAllByTestId('todo-print-anyway').map((b) => b.getAttribute('aria-label'))).toEqual([
      'Print Anyway: Lamp',
      'Print Anyway: Cube',
    ]);
  });

  it('names the printer when an entry without pictures lists several', async () => {
    const calls = recordStarts(30);
    const both: Job = { ...shortOnLeft, short_only_printer_ids: [1, 2] };
    render(<QueueTodoList todo={modelEntry([both], [left, right], false)} />);
    expect(screen.getAllByTestId('todo-print-anyway').map((b) => b.getAttribute('aria-label'))).toEqual([
      'Print Anyway: P1S left',
      'Print Anyway: P1S right',
    ]);
    fireEvent.click(screen.getByRole('button', { name: 'Print Anyway: P1S right' }));
    await waitFor(() => expect(calls).toEqual(['?printer_id=2']));
  });
});
