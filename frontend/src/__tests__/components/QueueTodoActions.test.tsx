/**
 * The other To do entries can be acted on in place (#3726): switch a smart
 * plug on again, edit or move a job, add a spool for a colour that is not in
 * stock. Each button only with its permission.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent, render as rtlRender } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '../../contexts/ToastContext';
import type { PrintQueueItem, QueueTodo, QueueTodoEntry } from '../../api/client';

const perms = { granted: new Set<string>(), ownerOk: (_owner: number | null | undefined) => true };

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
      canModify: (_r: string, _a: string, owner: number | null | undefined) =>
        (perms.granted.has('queue:update_all') || perms.granted.has('queue:update_own')) && perms.ownerOk(owner),
    }),
  };
});

const printModalProps = vi.fn();
vi.mock('../../components/PrintModal', () => ({
  PrintModal: (props: Record<string, unknown>) => {
    printModalProps(props);
    return <div data-testid="print-modal" />;
  },
}));
const formProps = vi.fn();
vi.mock('../../components/SpoolFormModal', () => ({
  SpoolFormModal: (props: Record<string, unknown>) => {
    formProps(props);
    return <div data-testid="spool-form-modal" />;
  },
}));

import { api } from '../../api/client';
import { QueueTodoList } from '../../components/QueueTodoList';

const job = { id: 5, name: 'Lamp', can_start: false };
const base = { jobs: [job], filaments: [], printers: [], detail: null };
const noStock: QueueTodoEntry = {
  ...base,
  kind: 'load_filament',
  filaments: [{ type: 'PLA', color: '#C8102E', color_name: 'Lava Red', no_stock: true }],
};
// Missing from the printer, but in stock.
const inStock: QueueTodoEntry = {
  ...noStock,
  filaments: [{ type: 'PLA', color: '#C8102E', color_name: 'Lava Red', no_stock: false }],
};
// Loaded, only too little of it.
const shortOnly: QueueTodoEntry = {
  ...noStock,
  filaments: [{ type: 'PLA', color: '#C8102E', color_name: 'Lava Red', no_stock: false, short: true }],
};
const powerOff: QueueTodoEntry = { ...base, kind: 'power_on_failed' };
const interlock: QueueTodoEntry = { ...base, kind: 'sensor_interlock', detail: 'Enclosure Door' };

const todoWith = (entries: QueueTodoEntry[]): QueueTodo => ({
  count: entries.length,
  groups: [{ printer_id: 3, printer_name: 'Shelf X1C', target_model: null, prepare: [], entries }],
});

const queueItem = { id: 5, created_by_id: 1, archive_id: 9, library_file_id: null, archive_name: 'Lamp' } as unknown as PrintQueueItem;

let client: QueryClient;
function renderList(entries: QueueTodoEntry[]) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  rtlRender(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <QueueTodoList todo={todoWith(entries)} overlayZIndex="z-[70]" />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return invalidate;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
  perms.granted = new Set();
  perms.ownerOk = () => true;
  vi.spyOn(api, 'getQueue').mockResolvedValue([queueItem]);
  vi.spyOn(api, 'getSpoolmanStatus').mockResolvedValue({ enabled: false, connected: false } as never);
});

describe('Switch on again', () => {
  it('looks the plug up, switches it on, says so and refreshes the list', async () => {
    perms.granted = new Set(['smart_plugs:read', 'smart_plugs:control']);
    const lookup = vi.spyOn(api, 'getSmartPlugByPrinter').mockResolvedValue({ id: 42 } as never);
    const control = vi.spyOn(api, 'controlSmartPlug').mockResolvedValue({ success: true } as never);
    const invalidate = renderList([powerOff]);
    fireEvent.click(screen.getByRole('button', { name: 'Switch on again' }));
    await waitFor(() => expect(control).toHaveBeenCalledWith(42, 'on'));
    expect(lookup).toHaveBeenCalledWith(3);
    expect(await screen.findByText('Switch-on command sent')).toBeInTheDocument();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['queue-todo'] });
  });

  it('says so when the printer has no plug, and switches nothing', async () => {
    perms.granted = new Set(['smart_plugs:read', 'smart_plugs:control']);
    vi.spyOn(api, 'getSmartPlugByPrinter').mockResolvedValue(null as never);
    const control = vi.spyOn(api, 'controlSmartPlug');
    renderList([powerOff]);
    fireEvent.click(screen.getByRole('button', { name: 'Switch on again' }));
    expect(await screen.findByText('No smart plug found for this printer')).toBeInTheDocument();
    expect(control).not.toHaveBeenCalled();
  });

  it('is absent with smart_plugs:control but without smart_plugs:read: the plug lookup would be refused', () => {
    perms.granted = new Set(['smart_plugs:control']);
    renderList([powerOff]);
    expect(screen.queryByRole('button', { name: 'Switch on again' })).toBeNull();
    expect(screen.getByTestId('todo-entry-power_on_failed')).toBeInTheDocument();
  });

  it('is absent with smart_plugs:read but without smart_plugs:control', () => {
    perms.granted = new Set(['smart_plugs:read']);
    renderList([powerOff]);
    expect(screen.queryByRole('button', { name: 'Switch on again' })).toBeNull();
  });

  it('is absent without smart_plugs:control, the entry stays as it was', () => {
    renderList([powerOff]);
    expect(screen.queryByRole('button', { name: 'Switch on again' })).toBeNull();
    expect(screen.getByTestId('todo-entry-power_on_failed')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open printer' })).toBeInTheDocument();
  });
});

describe('Edit job and Move to another printer', () => {
  it.each(['Edit job', 'Move to another printer'])('%s opens the queue edit dialog for that job above the panel', async (name) => {
    perms.granted = new Set(['queue:update_all']);
    const invalidate = renderList([noStock]);
    fireEvent.click(await screen.findByRole('button', { name }));
    await screen.findByTestId('print-modal');
    const props = printModalProps.mock.lastCall![0];
    expect(props).toMatchObject({ mode: 'edit-queue-item', archiveId: 9, queueItem, overlayZIndex: 'z-[70]' });
    props.onSuccess();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['queue-todo'] });
    props.onClose();
    await waitFor(() => expect(screen.queryByTestId('print-modal')).toBeNull());
  });

  it('is absent without a queue update permission', async () => {
    renderList([noStock]);
    await waitFor(() => expect(screen.getByTestId('todo-entry-load_filament')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Edit job' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Move to another printer' })).toBeNull();
    expect(api.getQueue).not.toHaveBeenCalled();
  });

  it('with queue:update_own is there for the user\'s own job only', async () => {
    perms.granted = new Set(['queue:update_own']);
    perms.ownerOk = (owner) => owner === 1;
    vi.spyOn(api, 'getQueue').mockResolvedValue([{ ...queueItem, created_by_id: 2 } as PrintQueueItem]);
    renderList([noStock]);
    await waitFor(() => expect(api.getQueue).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: 'Edit job' })).toBeNull();
  });

  it('with queue:update_own is there for the own job', async () => {
    perms.granted = new Set(['queue:update_own']);
    perms.ownerOk = (owner) => owner === 1;
    renderList([noStock]);
    expect(await screen.findByRole('button', { name: 'Edit job' })).toBeInTheDocument();
  });

  it('is offered on a missing filament that is in stock too', async () => {
    perms.granted = new Set(['queue:update_all']);
    renderList([inStock]);
    expect(await screen.findByRole('button', { name: 'Edit job' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Move to another printer' })).toBeInTheDocument();
  });

  it('is not offered on an entry that only has a short spool', async () => {
    perms.granted = new Set(['queue:update_all']);
    renderList([shortOnly]);
    await waitFor(() => expect(screen.getByTestId('todo-entry-load_filament')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Edit job' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Move to another printer' })).toBeNull();
  });

  it('offers no move for an "Any model" job, only edit', async () => {
    perms.granted = new Set(['queue:update_all']);
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const todo: QueueTodo = { count: 1, groups: [{ printer_id: null, printer_name: 'X1C', target_model: 'X1C', prepare: [], entries: [{ ...inStock, printers: [{ id: 3, name: 'Shelf X1C' }] }] }] };
    rtlRender(
      <QueryClientProvider client={client}>
        <MemoryRouter><ToastProvider><QueueTodoList todo={todo} /></ToastProvider></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('button', { name: 'Edit job' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move to another printer' })).toBeNull();
  });
});

describe('Add spool', () => {
  it('opens the new-spool form started with the filament', async () => {
    perms.granted = new Set(['inventory:create']);
    renderList([noStock]);
    fireEvent.click(await screen.findByRole('button', { name: 'Add spool' }));
    await screen.findByTestId('spool-form-modal');
    expect(formProps.mock.lastCall![0]).toMatchObject({
      mode: 'create',
      overlayZIndex: 'z-[70]',
      initialValues: { material: 'PLA', color_name: 'Lava Red', rgba: 'C8102EFF' },
    });
  });

  it('is absent without inventory:create', async () => {
    renderList([noStock]);
    await waitFor(() => expect(screen.getByTestId('todo-entry-load_filament')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Add spool' })).toBeNull();
  });

  it('is absent with Spoolman', async () => {
    perms.granted = new Set(['inventory:create']);
    vi.spyOn(api, 'getSpoolmanStatus').mockResolvedValue({ enabled: true, connected: true } as never);
    renderList([noStock]);
    await waitFor(() => expect(api.getSpoolmanStatus).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: 'Add spool' })).toBeNull();
  });

  it('is absent on an entry whose filament is in stock', async () => {
    // (missing from the printer, but there is a spool to load)
    perms.granted = new Set(['inventory:create']);
    renderList([inStock]);
    await waitFor(() => expect(screen.getByTestId('todo-entry-load_filament')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Add spool' })).toBeNull();
  });
});

describe('a sensor interlock', () => {
  it('stays a hint with the link, whatever is granted', () => {
    perms.granted = new Set(['smart_plugs:read', 'smart_plugs:control', 'queue:update_all', 'inventory:create']);
    renderList([interlock]);
    expect(screen.getByText('Enclosure Door')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open printer' })).toBeInTheDocument();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });
});
