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
  plate_id?: number | null;
  ams_mapping?: number[];
  filament_overrides?: Array<Record<string, unknown>>;
};
let posted: Body[];
let patched: Body[];

const PLATES = {
  is_multi_plate: true,
  plates: [1, 2].map((index) => ({
    index,
    name: `Plate ${index}`,
    has_thumbnail: false,
    thumbnail_url: null,
    objects: ['A'],
    filaments: [{ type: 'PLA', color: '#FFFFFF' }],
    print_time_seconds: 600,
    filament_used_grams: 50,
  })),
};

const LOADED_LAVA_RED = { id: 2, tray_type: 'PLA', tray_color: 'C0392BFF', tray_info_idx: 'GFA01', tray_sub_brands: 'PLA Matte' };

function mockBackend(
  opts: {
    flag?: boolean;
    loadedFirst?: boolean;
    status?: unknown;
    reqs?: unknown[];
    plates?: boolean;
    available?: unknown[];
  } = {},
) {
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
    http.get('/api/v1/printers/:id/status', () => HttpResponse.json(opts.status ?? STATUS)),
    http.get('/api/v1/printers/available-filaments', () => HttpResponse.json(opts.available ?? [])),
    http.get('/api/v1/printers/inventory-filaments', () =>
      HttpResponse.json({ inventory_available: true, filaments: [LAVA_RED] }),
    ),
    http.get('/api/v1/archives/:id', () => HttpResponse.json({ id: 1, sliced_for_model: null })),
    http.get('/api/v1/archives/:id/plates', () =>
      HttpResponse.json(opts.plates ? PLATES : { is_multi_plate: false, plates: [] }),
    ),
    http.get('/api/v1/archives/:id/filament-requirements', () => HttpResponse.json({ filaments: opts.reqs ?? REQS })),
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

  it('under ASAP the mapping says the inventory colours come with Queue or Schedule', async () => {
    const user = userEvent.setup();
    renderCreate();

    await slotTrigger(2);
    const hint = await screen.findByTestId('inventory-now-hint');
    expect(hint).toHaveTextContent('Colours from the inventory can be picked with Queue or Schedule.');

    // Once queued the group itself is there, so the pointer to it goes.
    await user.click(screen.getByRole('button', { name: /^queue$/i }));
    await waitFor(() => expect(screen.queryByTestId('inventory-now-hint')).not.toBeInTheDocument());
  });

  it('says nothing under ASAP with "Show inventory colours" off', async () => {
    mockBackend({ flag: false });
    renderCreate();

    await slotTrigger(2);
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByTestId('inventory-now-hint')).not.toBeInTheDocument();
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

const forceBoxes = () => screen.queryAllByText('Force color match');

describe('PrintModal: a pick is always forced (#3649)', () => {
  beforeEach(() => mockBackend());

  it('offers no force-colour box for the picked slot, so there is no way to send it unforced', async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.click(screen.getByRole('button', { name: /^queue$/i }));
    await slotTrigger(2);
    expect(forceBoxes()).toHaveLength(2);

    await pickLavaRed(await slotTrigger(2));
    await screen.findByText('(Waits for filament)');
    expect(forceBoxes()).toHaveLength(1);
  });

  it('shows no force-colour box in the several-printer panel either', async () => {
    const user = userEvent.setup();
    await renderCreateWithTwoPrinters(user);
    await user.click(await screen.findByRole('button', { name: /^queue$/i }));
    const triggers = await waitFor(() => {
      const all = screen.getAllByRole('combobox', { name: /filament override for/i });
      expect(all).toHaveLength(2);
      return all;
    });
    await pickLavaRed(triggers[1]);

    await screen.findByText(/waits until this filament is loaded on each selected printer/);
    expect(forceBoxes()).toHaveLength(0);
  });

  it('keeps a manual tick when the pick is given up, and unticks an automatic one', async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.click(screen.getByRole('button', { name: /^queue$/i }));
    await slotTrigger(2);

    const giveUp = async () => {
      const listbox = await openList(await slotTrigger(2));
      fireEvent.click(within(listbox).getAllByText(/PLA Basic/)[1]);
      await waitFor(() => expect(forceBoxes()).toHaveLength(2));
    };
    const tickOf = (slot: 1 | 2) => screen.getAllByRole('checkbox', { name: /force color match/i })[slot - 1] as HTMLInputElement;

    // Automatic tick (the pick forced the slot): gone with the pick.
    await pickLavaRed(await slotTrigger(2));
    await giveUp();
    expect(tickOf(2).checked).toBe(false);

    // The user ticked the box before picking: it stays.
    await user.click(tickOf(2));
    await pickLavaRed(await slotTrigger(2));
    await giveUp();
    expect(tickOf(2).checked).toBe(true);
  });
});

describe('PrintModal: a pick carried over from model mode (#3649)', () => {
  const LOADED_RED_PLA = { type: 'PLA', color: '#FF0000', tray_info_idx: 'GFA00', tray_sub_brands: 'PLA Basic', extruder_id: null };

  const toModelMode = async (user: ReturnType<typeof userEvent.setup>) => {
    render(<PrintModal mode="create" archiveId={1} archiveName="Bracket" onClose={() => {}} />);
    await user.click(await screen.findByRole('button', { name: /any model/i }));
    const modelSelect = await waitFor(() => {
      const select = screen
        .getAllByRole('combobox')
        .find((el) => (el as HTMLSelectElement).options?.[0]?.text === 'Select a model...');
      if (!select) throw new Error('target model select not rendered');
      return select as HTMLSelectElement;
    });
    await user.selectOptions(modelSelect, 'A1M');
  };
  const overrideTrigger = async (slot: 1 | 2) =>
    (await waitFor(() => {
      const all = screen.getAllByRole('combobox', { name: /filament override for/i });
      expect(all).toHaveLength(2);
      return all;
    }))[slot - 1];
  const toPrinter = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(await screen.findByRole('button', { name: /specific printer/i }));
    await user.click(await screen.findByText('A1 Mini North'));
  };

  it('stays a forced pick when the box was unticked, moves "Print now" to the queue and queues -1', async () => {
    mockBackend({ available: [LOADED_RED_PLA] });
    const user = userEvent.setup();
    await toModelMode(user);
    await pickLavaRed(await overrideTrigger(2));
    // Model mode lets the user untick the automatic tick.
    const box = screen.getAllByRole('checkbox', { name: /force color match/i })[1] as HTMLInputElement;
    await waitFor(() => expect(box.checked).toBe(true));
    await user.click(box);
    expect(box.checked).toBe(false);

    await toPrinter(user);

    expect(await screen.findByText('(Waits for filament)')).toBeInTheDocument();
    // ASAP was selected; with the pick standing the job went to the queue instead.
    await waitFor(() => expect(screen.getByRole('button', { name: /asap/i })).toBeDisabled());
    await submit(user);
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].ams_mapping).toEqual([0, -1]);
    expect(posted[0].filament_overrides).toEqual([
      expect.objectContaining({ slot_id: 2, color: '#C0392B', tray_info_idx: 'GFA01', force_color_match: true }),
    ]);
  });

  it('becomes that tray when its colour is loaded on the selected printer, and ASAP stays open', async () => {
    mockBackend({
      available: [LOADED_RED_PLA],
      status: { ...STATUS, ams: [{ id: 0, tray: [...STATUS.ams[0].tray, LOADED_LAVA_RED] }] },
    });
    const user = userEvent.setup();
    await toModelMode(user);
    await pickLavaRed(await overrideTrigger(2));
    await toPrinter(user);

    await waitFor(() => expect(screen.getByRole('button', { name: /asap/i })).toBeEnabled());
    expect(screen.queryByText('(Waits for filament)')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^queue$/i }));
    await submit(user);

    await waitFor(() => expect(posted).toHaveLength(1));
    // The colour sits in tray 2 now: a tray, no -1.
    expect(posted[0].ams_mapping).toEqual([0, 2]);
    expect(posted[0].filament_overrides).toEqual([
      expect.objectContaining({ slot_id: 2, color: '#C0392B', force_color_match: true }),
    ]);
  });

  it('shows a loaded colour carried over to several printers nowhere in the inventory panel', async () => {
    mockBackend({ available: [LOADED_RED_PLA] });
    const user = userEvent.setup();
    await toModelMode(user);
    const listbox = await openList(await overrideTrigger(1));
    fireEvent.click(within(listbox).getAllByRole('option').find((o) => o.getAttribute('data-value') === 'PLA|#FF0000')!);

    await user.click(await screen.findByRole('button', { name: /specific printer/i }));
    await user.click(await screen.findByText('A1 Mini North'));
    await user.click(await screen.findByText('A1 Mini South'));
    await user.click(await screen.findByRole('button', { name: /^queue$/i }));

    const panel = await screen.findByText('Filament from inventory');
    expect(panel).toBeInTheDocument();
    const triggers = await waitFor(() => {
      const all = screen.getAllByRole('combobox', { name: /filament override for/i });
      expect(all).toHaveLength(2);
      return all;
    });
    expect(triggers[0].textContent).not.toMatch(/FF0000|Red/i);
    expect(screen.queryByText(/waits until this filament is loaded/)).not.toBeInTheDocument();
  });
});

describe('PrintModal: several plates (#3649)', () => {
  beforeEach(() => mockBackend({ plates: true, flag: true }));

  const bothPlates = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(await screen.findByText('Plate 2'));
    await user.click(screen.getByRole('button', { name: /^queue$/i }));
  };
  /** The per-plate mapping panels start collapsed; open them all. */
  const openPlatePanels = async (user: ReturnType<typeof userEvent.setup>) => {
    const headers = await waitFor(() => {
      const all = screen.getAllByRole('button', { name: /filament mapping/i });
      expect(all).toHaveLength(2);
      return all;
    });
    for (const header of headers) await user.click(header);
    return await waitFor(() => {
      const all = screen.getAllByRole('combobox', { name: /slot for/i });
      expect(all).toHaveLength(4);
      return all;
    });
  };

  it('one printer: every plate gets -1 at the slot and the forced override', async () => {
    const user = userEvent.setup();
    render(<PrintModal mode="create" archiveId={1} archiveName="Bracket" initialSelectedPrinterIds={[1]} onClose={() => {}} />);
    await bothPlates(user);
    const triggers = await openPlatePanels(user);
    await pickLavaRed(triggers[1]);
    await submit(user);

    await waitFor(() => expect(posted).toHaveLength(2));
    expect(posted.map((p) => p.plate_id).sort()).toEqual([1, 2]);
    for (const body of posted) {
      expect(body.ams_mapping).toEqual([0, -1]);
      expect(body.filament_overrides).toEqual([
        expect.objectContaining({ slot_id: 2, color: '#C0392B', force_color_match: true }),
      ]);
    }
  });

  it('several printers: no tray mapping at all, only the forced override', async () => {
    const user = userEvent.setup();
    render(<PrintModal mode="create" archiveId={1} archiveName="Bracket" onClose={() => {}} />);
    await user.click(await screen.findByText('A1 Mini North'));
    await user.click(await screen.findByText('A1 Mini South'));
    await bothPlates(user);
    const triggers = await waitFor(() => {
      const all = screen.getAllByRole('combobox', { name: /filament override for/i });
      expect(all.length).toBeGreaterThanOrEqual(2);
      return all;
    });
    await pickLavaRed(triggers[1]);
    await submit(user);

    await waitFor(() => expect(posted).toHaveLength(4));
    for (const body of posted) {
      expect(body.filament_overrides).toEqual([
        expect.objectContaining({ slot_id: 2, color: '#C0392B', force_color_match: true }),
      ]);
    }
    expect(posted.map((p) => `${p.printer_id}:${p.plate_id}`).sort()).toEqual(['1:1', '1:2', '2:1', '2:2']);
  });

  it('a plate switch clears the pick and its tick', async () => {
    const user = userEvent.setup();
    render(<PrintModal mode="create" archiveId={1} archiveName="Bracket" initialSelectedPrinterIds={[1]} onClose={() => {}} />);
    await user.click(await screen.findByRole('button', { name: /^queue$/i }));
    await pickLavaRed(await slotTrigger(2));
    await screen.findByText('(Waits for filament)');

    await user.click(await screen.findByText('Plate 2'));

    await waitFor(() => expect(screen.queryByText('(Waits for filament)')).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: /asap/i })).toBeEnabled();
    const triggers = await openPlatePanels(user);
    expect(triggers[1].textContent).not.toMatch(/Lava Red/);
    for (const box of screen.getAllByRole('checkbox', { name: /force color match/i })) {
      expect((box as HTMLInputElement).checked).toBe(false);
    }
  });
});

describe('PrintModal: slots the file does not print (#3649)', () => {
  it('a stored pick for a slot outside the file blocks nothing and is not sent', async () => {
    mockBackend({ reqs: REQS });
    const stale = {
      id: 9,
      printer_id: 1,
      target_model: null,
      status: 'pending',
      archive_id: 1,
      manual_start: false,
      ams_mapping: [0, 1, -1],
      filament_overrides: [
        { slot_id: 3, type: 'PLA', color: '#C0392B', color_name: 'Lava Red', tray_info_idx: 'GFA01', force_color_match: true },
      ],
    } as never;
    const user = userEvent.setup();
    render(<PrintModal mode="edit-queue-item" archiveId={1} archiveName="Bracket" queueItem={stale} onClose={() => {}} />);

    await user.click(await screen.findByRole('button', { name: /filament mapping/i }));
    await slotTrigger(2);
    expect(screen.queryByText('(Waits for filament)')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /asap/i })).toBeEnabled();
    expect(screen.queryByText(/A colour from the inventory is not loaded yet/)).not.toBeInTheDocument();
  });
});

describe('PrintModal: the mapping of a pick (#3649)', () => {
  const THREE = [
    { slot_id: 1, type: 'PLA', color: '#FFFFFF', tray_info_idx: 'GFA00', used_grams: 20, used_meters: 6 },
    { slot_id: 2, type: 'PLA', color: '#000000', tray_info_idx: 'GFA00', used_grams: 30, used_meters: 9 },
    { slot_id: 3, type: 'PLA', color: '#00FF00', tray_info_idx: 'GFA00', used_grams: 10, used_meters: 3 },
  ];

  it('several printers: a pick in the middle is -1 and the slots around it keep their trays', async () => {
    mockBackend({ reqs: THREE });
    const user = userEvent.setup();
    await renderCreateWithTwoPrinters(user);
    await user.click(await screen.findByRole('button', { name: /^queue$/i }));
    const triggers = await waitFor(() => {
      const all = screen.getAllByRole('combobox', { name: /filament override for/i });
      expect(all).toHaveLength(3);
      return all;
    });
    await pickLavaRed(triggers[1]);
    await submit(user);

    await waitFor(() => expect(posted).toHaveLength(2));
    for (const body of posted) expect(body.ams_mapping).toEqual([0, -1, 1]);
  });

  it('several printers: a pick on the last slot pads the mapping the matcher left short', async () => {
    mockBackend({ reqs: THREE });
    const user = userEvent.setup();
    await renderCreateWithTwoPrinters(user);
    await user.click(await screen.findByRole('button', { name: /^queue$/i }));
    const triggers = await waitFor(() => {
      const all = screen.getAllByRole('combobox', { name: /filament override for/i });
      expect(all).toHaveLength(3);
      return all;
    });
    await pickLavaRed(triggers[2]);
    await submit(user);

    await waitFor(() => expect(posted).toHaveLength(2));
    for (const body of posted) expect(body.ams_mapping).toEqual([0, 1, -1]);
  });

  it('a dual-nozzle printer: the pick is -1, the other slot keeps the tray on its own nozzle', async () => {
    const dual = {
      ...STATUS,
      ams: [
        { id: 0, tray: [{ id: 0, tray_type: 'PLA', tray_color: 'FFFFFFFF', tray_info_idx: 'GFA00', tray_sub_brands: 'PLA Basic' }] },
        { id: 1, tray: [{ id: 0, tray_type: 'PLA', tray_color: '00FF00FF', tray_info_idx: 'GFA00', tray_sub_brands: 'PLA Basic' }] },
      ],
      ams_extruder_map: { '0': 1, '1': 0 },
    };
    mockBackend({
      status: dual,
      reqs: [
        { ...REQS[0], nozzle_id: 1 },
        { ...REQS[1], nozzle_id: 0 },
      ],
    });
    const user = userEvent.setup();
    renderCreate();
    await user.click(screen.getByRole('button', { name: /^queue$/i }));
    await pickLavaRed(await slotTrigger(2));
    await submit(user);

    await waitFor(() => expect(posted).toHaveLength(1));
    // Slot 1 (white, left nozzle) is on AMS 0, which feeds the left nozzle; slot 2 waits.
    expect(posted[0].ams_mapping).toEqual([0, -1]);
    expect(posted[0].filament_overrides).toEqual([expect.objectContaining({ slot_id: 2, force_color_match: true })]);
  });
});
