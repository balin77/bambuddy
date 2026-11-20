/**
 * PrintModal: a colour from the inventory for a specific printer (#3649).
 *
 * One selected printer: the slot dropdown gets the inventory group (Queue and
 * Schedule only). Several: the colour panel reduced to the inventory. A pick is
 * the forced override of its slot plus -1 at that slot of each printer's mapping;
 * "ASAP" is blocked while one stands; an edited job comes back with its pick.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { screen, waitFor, fireEvent, within, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { PrintModal } from '../../components/PrintModal';

const PRINTERS = [
  { id: 1, name: 'A1 Mini North', model: 'A1M', ip_address: '10.0.0.1', enabled: true, is_active: true },
  { id: 2, name: 'A1 Mini South', model: 'A1M', ip_address: '10.0.0.2', enabled: true, is_active: true },
];

const STATUS = {
  connected: true,
  state: 'IDLE',
  ams: [
    {
      id: 0,
      tray: [
        { id: 0, tray_type: 'PLA', tray_color: 'FFFFFFFF', tray_info_idx: 'GFA00', tray_sub_brands: 'PLA Basic' },
        { id: 1, tray_type: 'PLA', tray_color: '00FF00FF', tray_info_idx: 'GFA00', tray_sub_brands: 'PLA Basic' },
      ],
    },
  ],
  vt_tray: [],
  ams_extruder_map: {},
};

const LAVA_RED = {
  type: 'PLA',
  color: '#C0392B',
  tray_info_idx: 'GFA01',
  subtype: 'Matte',
  color_name: 'Lava Red',
  rgba: 'C0392BFF',
  extra_colors: null,
  effect_type: null,
  spool_count: 2,
  remaining_grams: 1400,
};

const REQS = [
  { slot_id: 1, type: 'PLA', color: '#FFFFFF', tray_info_idx: 'GFA00', used_grams: 20, used_meters: 6 },
  { slot_id: 2, type: 'PLA', color: '#000000', tray_info_idx: 'GFA00', used_grams: 30, used_meters: 9 },
];

type Body = {
  printer_id: number;
  ams_mapping?: number[];
  filament_overrides?: Array<Record<string, unknown>>;
};
let posted: Body[];
let patched: Body[];

function mockBackend(opts: { flag?: boolean; loadedFirst?: boolean } = {}) {
  posted = [];
  patched = [];
  server.use(
    http.get('/api/v1/settings/', () =>
      HttpResponse.json({
        filament_override_inventory: opts.flag ?? true,
        queue_loaded_filament_first: opts.loadedFirst ?? false,
      }),
    ),
    http.get('/api/v1/printers/', () => HttpResponse.json(PRINTERS)),
    http.get('/api/v1/printers/:id/status', () => HttpResponse.json(STATUS)),
    http.get('/api/v1/printers/inventory-filaments', () =>
      HttpResponse.json({ inventory_available: true, filaments: [LAVA_RED] }),
    ),
    http.get('/api/v1/archives/:id', () => HttpResponse.json({ id: 1, sliced_for_model: null })),
    http.get('/api/v1/archives/:id/plates', () => HttpResponse.json({ is_multi_plate: false, plates: [] })),
    http.get('/api/v1/archives/:id/filament-requirements', () => HttpResponse.json({ filaments: REQS })),
    http.post('/api/v1/queue/', async ({ request }) => {
      posted.push((await request.json()) as Body);
      return HttpResponse.json({ id: posted.length, status: 'pending' });
    }),
    http.patch('/api/v1/queue/:id', async ({ request }) => {
      patched.push((await request.json()) as Body);
      return HttpResponse.json({ id: 9, status: 'pending' });
    }),
  );
}

const renderCreate = () =>
  render(<PrintModal mode="create" archiveId={1} archiveName="Bracket" initialSelectedPrinterIds={[1]} onClose={() => {}} />);

/** The printer list is hidden when printers are preselected, so several are picked by hand. */
const renderCreateWithTwoPrinters = async (user: ReturnType<typeof userEvent.setup>) => {
  render(<PrintModal mode="create" archiveId={1} archiveName="Bracket" onClose={() => {}} />);
  await user.click(await screen.findByText('A1 Mini North'));
  await user.click(await screen.findByText('A1 Mini South'));
};

const submit = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(document.querySelector('button[type="submit"]') as HTMLElement);

const slotTrigger = async (slot: 1 | 2) =>
  (await waitFor(() => {
    const all = screen.getAllByRole('combobox', { name: /slot for/i });
    expect(all).toHaveLength(2);
    return all;
  }))[slot - 1];

const openList = async (trigger: HTMLElement) => {
  fireEvent.click(trigger);
  return await waitFor(() => screen.getByRole('listbox'));
};

const pickLavaRed = async (trigger: HTMLElement) => {
  const listbox = await openList(trigger);
  fireEvent.click(await within(listbox).findByText(/Lava Red/));
};

afterEach(() => cleanup());

describe('PrintModal: inventory colour for one printer (#3649)', () => {
  beforeEach(() => mockBackend());

  it('offers the group only once the job is queued or scheduled, not under ASAP', async () => {
    const user = userEvent.setup();
    renderCreate();

    // "ASAP" is the default: a print that starts at once can only use what is loaded.
    const listbox = await openList(await slotTrigger(2));
    expect(within(listbox).queryByText('From inventory (not loaded)')).not.toBeInTheDocument();
    fireEvent.keyDown(listbox, { key: 'Escape' });

    await user.click(screen.getByRole('button', { name: /^queue$/i }));
    const queued = await openList(await slotTrigger(2));
    expect(await within(queued).findByText('From inventory (not loaded)')).toBeInTheDocument();
    expect(within(queued).getByText(/Lava Red/)).toBeInTheDocument();
  });

  it('offers no group with "Show inventory colours" off', async () => {
    mockBackend({ flag: false });
    const user = userEvent.setup();
    renderCreate();
    await user.click(screen.getByRole('button', { name: /^queue$/i }));

    const listbox = await openList(await slotTrigger(2));
    await new Promise((r) => setTimeout(r, 100));
    expect(within(listbox).queryByText('From inventory (not loaded)')).not.toBeInTheDocument();
  });

  it('a pick reads "Waits for filament", blocks ASAP with its reason, and says how the job starts', async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.click(screen.getByRole('button', { name: /^queue$/i }));
    await pickLavaRed(await slotTrigger(2));

    expect(await screen.findByText('(Waits for filament)')).toBeInTheDocument();
    expect(
      screen.getByText('The job waits until this filament is loaded on A1 Mini North. Press Start once it is loaded.'),
    ).toBeInTheDocument();
    const asap = screen.getByRole('button', { name: /asap/i });
    expect(asap).toBeDisabled();
    expect(screen.getByText(/A colour from the inventory is not loaded yet\. Queue or schedule the job/)).toBeInTheDocument();
    // Giving the pick up (a loaded slot again) frees the option.
    const listbox = await openList(await slotTrigger(2));
    fireEvent.click(within(listbox).getAllByText(/PLA Basic/)[1]);
    await waitFor(() => expect(screen.getByRole('button', { name: /asap/i })).toBeEnabled());
  });

  it('queues the override and -1 at the picked slot; the other slot keeps its tray', async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.click(screen.getByRole('button', { name: /^queue$/i }));
    await pickLavaRed(await slotTrigger(2));
    await submit(user);

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].printer_id).toBe(1);
    expect(posted[0].ams_mapping).toEqual([0, -1]);
    expect(posted[0].filament_overrides).toEqual([
      expect.objectContaining({
        slot_id: 2,
        type: 'PLA',
        color: '#C0392B',
        color_name: 'Lava Red',
        tray_info_idx: 'GFA01',
        force_color_match: true,
      }),
    ]);
  });

  it('without a pick the request is what it was: no override, a tray for every slot', async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.click(screen.getByRole('button', { name: /^queue$/i }));
    await slotTrigger(2);
    await submit(user);

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].ams_mapping).toEqual([0, 1]);
    expect(posted[0].filament_overrides).toBeUndefined();
  });
});

describe('PrintModal: inventory colour for several printers (#3649)', () => {
  beforeEach(() => mockBackend());

  const panelTrigger = async (slot: 1 | 2) =>
    (await waitFor(() => {
      const all = screen.getAllByRole('combobox', { name: /filament override for/i });
      expect(all).toHaveLength(2);
      return all;
    }))[slot - 1];

  it('shows the inventory panel for queue jobs only', async () => {
    const user = userEvent.setup();
    await renderCreateWithTwoPrinters(user);
    expect(screen.queryByText('Filament from inventory')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^queue$/i }));
    expect(await screen.findByText('Filament from inventory')).toBeInTheDocument();
    // No loaded rows: the printers hold different filament.
    const listbox = await openList(await panelTrigger(2));
    expect(await within(listbox).findByText('From inventory (not loaded)')).toBeInTheDocument();
    expect(within(listbox).queryByText('Loaded now')).not.toBeInTheDocument();
  });

  it('queues every printer with the override and -1 at the slot in its own mapping', async () => {
    const user = userEvent.setup();
    await renderCreateWithTwoPrinters(user);
    await user.click(await screen.findByRole('button', { name: /^queue$/i }));
    await pickLavaRed(await panelTrigger(2));
    expect(
      await screen.findByText('The job waits until this filament is loaded on each selected printer. Press Start once it is loaded.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /asap/i })).toBeDisabled();
    await submit(user);

    await waitFor(() => expect(posted).toHaveLength(2));
    expect(posted.map((p) => p.printer_id).sort()).toEqual([1, 2]);
    for (const body of posted) {
      expect(body.ams_mapping).toEqual([0, -1]);
      expect(body.filament_overrides).toEqual([
        expect.objectContaining({ slot_id: 2, color: '#C0392B', tray_info_idx: 'GFA01', force_color_match: true }),
      ]);
    }
  });

  it('keeps the pick when the selection goes back to one printer', async () => {
    const user = userEvent.setup();
    await renderCreateWithTwoPrinters(user);
    await user.click(await screen.findByRole('button', { name: /^queue$/i }));
    await pickLavaRed(await panelTrigger(2));
    await user.click(await screen.findByText('A1 Mini South'));

    expect(await screen.findByText('(Waits for filament)')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /filament mapping/i }));
    expect((await slotTrigger(2)).textContent).toMatch(/Lava Red/);
  });
});

describe('PrintModal: editing a job that waits for an inventory colour (#3649)', () => {
  beforeEach(() => mockBackend({ loadedFirst: true }));

  const job = {
    id: 9,
    printer_id: 1,
    target_model: null,
    status: 'pending',
    archive_id: 1,
    manual_start: false,
    ams_mapping: [0, -1],
    filament_overrides: [
      { slot_id: 2, type: 'PLA', color: '#C0392B', color_name: 'Lava Red', tray_info_idx: 'GFA01', force_color_match: true },
    ],
  } as never;

  it('comes back as a pick, and a save keeps the -1 and the override', async () => {
    const user = userEvent.setup();
    render(<PrintModal mode="edit-queue-item" archiveId={1} archiveName="Bracket" queueItem={job} onClose={() => {}} />);

    // The mapping panel starts collapsed when editing.
    await user.click(await screen.findByRole('button', { name: /filament mapping/i }));
    expect((await slotTrigger(2)).textContent).toMatch(/Lava Red/);
    expect(await screen.findByText('(Waits for filament)')).toBeInTheDocument();
    // "Loaded filament first" is on: nothing to press by hand.
    expect(screen.getByText('The job waits until this filament is loaded on A1 Mini North.')).toBeInTheDocument();
    await submit(user);

    await waitFor(() => expect(patched).toHaveLength(1));
    expect(patched[0].ams_mapping).toEqual([0, -1]);
    expect(patched[0].filament_overrides).toEqual([
      expect.objectContaining({ slot_id: 2, color: '#C0392B', tray_info_idx: 'GFA01', force_color_match: true }),
    ]);
  });
});
