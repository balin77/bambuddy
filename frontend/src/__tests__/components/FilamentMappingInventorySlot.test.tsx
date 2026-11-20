/**
 * FilamentMapping: a slot of a pinned printer can wait for a colour from the
 * inventory that is not loaded yet (#3649).
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { screen, waitFor, cleanup, fireEvent, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { FilamentMapping } from '../../components/PrintModal/FilamentMapping';
import type { PrinterStatus, InventoryFilament } from '../../api/client';
import type { FilamentOverrideEntry } from '../../components/PrintModal/inventoryOptions';

const REQS = {
  filaments: [
    { slot_id: 1, type: 'PLA', color: '#FFFFFF', used_grams: 20, used_meters: 6 },
    { slot_id: 2, type: 'PLA', color: '#000000', used_grams: 30, used_meters: 9 },
  ],
};

const LAVA_RED: InventoryFilament = {
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
// Loaded already: never offered as "not loaded".
const LOADED_WHITE: InventoryFilament = { ...LAVA_RED, color: '#FFFFFF', color_name: 'Cotton White', rgba: 'FFFFFFFF' };

const STATUS = {
  id: 1,
  name: 'A1 Mini',
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
} as unknown as PrinterStatus;

const PICK: FilamentOverrideEntry = {
  type: 'PLA',
  color: '#C0392B',
  tray_info_idx: 'GFA01',
  fromInventory: true,
  colorName: 'Lava Red',
};

function mockPrinter(status: PrinterStatus = STATUS) {
  server.use(
    http.get('/api/v1/printers/:id/status', () => HttpResponse.json(status)),
    http.get('/api/v1/settings/', () => HttpResponse.json({ queue_loaded_filament_first: false })),
  );
}

function renderPanel(props: Partial<React.ComponentProps<typeof FilamentMapping>> = {}) {
  const onManualMappingChange = vi.fn();
  const onInventoryPick = vi.fn();
  const result = render(
    <FilamentMapping
      printerId={1}
      printerName="A1 Mini"
      blockedFilaments={[]}
      filamentReqs={REQS}
      manualMappings={{}}
      onManualMappingChange={onManualMappingChange}
      currencySymbol="$"
      defaultCostPerKg={20}
      defaultExpanded
      inventoryFilaments={[LAVA_RED, LOADED_WHITE]}
      onInventoryPick={onInventoryPick}
      {...props}
    />,
  );
  return { ...result, onManualMappingChange, onInventoryPick };
}

async function openSecondRow() {
  const triggers = await waitFor(() => {
    const all = screen.getAllByRole('combobox');
    expect(all).toHaveLength(2);
    return all;
  });
  fireEvent.click(triggers[1]);
  return await waitFor(() => screen.getByRole('listbox'));
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('FilamentMapping: inventory group', () => {
  it('offers the not-loaded entries in a second group below the loaded slots', async () => {
    mockPrinter();
    renderPanel();

    const listbox = await openSecondRow();

    expect(within(listbox).getByText('Loaded now')).toBeInTheDocument();
    expect(within(listbox).getByText('From inventory (not loaded)')).toBeInTheDocument();
    expect(within(listbox).getByText(/Lava Red/)).toBeInTheDocument();
    // Cotton White is loaded on slot A1: it is a loaded row, not an inventory one.
    expect(within(listbox).queryByText(/Cotton White/)).not.toBeInTheDocument();
  });

  it('shows no group without a list to pick from', async () => {
    mockPrinter();
    renderPanel({ inventoryFilaments: [] });

    const listbox = await openSecondRow();

    expect(within(listbox).queryByText('From inventory (not loaded)')).not.toBeInTheDocument();
    expect(within(listbox).queryByText('Loaded now')).not.toBeInTheDocument();
  });

  it('hands a pick back as an override and drops a tray chosen by hand for the slot', async () => {
    mockPrinter();
    const { onInventoryPick, onManualMappingChange } = renderPanel({ manualMappings: { 1: 0, 2: 1 } });

    const listbox = await openSecondRow();
    fireEvent.click(within(listbox).getByText(/Lava Red/));

    expect(onInventoryPick).toHaveBeenCalledWith(2, {
      type: 'PLA',
      color: '#C0392B',
      tray_info_idx: 'GFA01',
      fromInventory: true,
      colorName: 'Lava Red',
    });
    expect(onManualMappingChange).toHaveBeenCalledWith({ 1: 0 });
  });
});

describe('FilamentMapping: a slot waiting for the inventory colour', () => {
  it('reads "Waits for filament", not "Ready", and keeps the file colour on the left', async () => {
    mockPrinter();
    renderPanel({ inventoryPicks: { 2: PICK }, manualMappings: { 1: 0 } });

    await waitFor(() => expect(screen.getByText('(Waits for filament)')).toBeInTheDocument());
    expect(screen.queryByText('(Ready)')).not.toBeInTheDocument();
    // The slot's picker shows the pick; the loaded A2 is not auto-matched for it.
    const triggers = screen.getAllByRole('combobox');
    expect(triggers[1].textContent).toMatch(/Lava Red/);
    expect(triggers[1].getAttribute('title')).toBe('Waits for filament');
  });

  it('says the job waits on the printer, and to press Start with Loaded filament first off', async () => {
    mockPrinter();
    renderPanel({ inventoryPicks: { 2: PICK } });

    expect(
      await screen.findByText(
        'The job waits until this filament is loaded on A1 Mini. Press Start once it is loaded.',
      ),
    ).toBeInTheDocument();
  });

  it('leaves out the Start sentence with Loaded filament first on', async () => {
    server.use(
      http.get('/api/v1/printers/:id/status', () => HttpResponse.json(STATUS)),
      http.get('/api/v1/settings/', () => HttpResponse.json({ queue_loaded_filament_first: true })),
    );
    renderPanel({ inventoryPicks: { 2: PICK } });

    expect(await screen.findByText('The job waits until this filament is loaded on A1 Mini.')).toBeInTheDocument();
  });

  it('keeps the nozzle badge and says into which nozzle the colour goes', async () => {
    mockPrinter();
    renderPanel({
      filamentReqs: {
        filaments: [
          { slot_id: 1, type: 'PLA', color: '#FFFFFF', used_grams: 20, used_meters: 6, nozzle_id: 0 },
          { slot_id: 2, type: 'PLA', color: '#000000', used_grams: 30, used_meters: 9, nozzle_id: 1 },
        ],
      },
      inventoryPicks: { 2: PICK },
    });

    expect(await screen.findByText(/Load it into the AMS of the left nozzle\./)).toBeInTheDocument();
    expect(screen.getByText('L')).toBeInTheDocument();
    expect(screen.getByText('R')).toBeInTheDocument();
  });

  it('prices the loaded slots only and says the estimate is partial', async () => {
    mockPrinter();
    renderPanel({ inventoryPicks: { 2: PICK } });

    // Slot 1 (20 g at 20 per kg) is priced; slot 2 has no spool yet.
    expect(await screen.findByText('$0.40')).toBeInTheDocument();
    expect(screen.getByText('Estimate without the filaments still to load.')).toBeInTheDocument();
  });

  it('gives the pick up when a loaded slot is chosen again', async () => {
    mockPrinter();
    const { onInventoryPick, onManualMappingChange } = renderPanel({ inventoryPicks: { 2: PICK } });

    const listbox = await openSecondRow();
    fireEvent.click(within(listbox).getAllByText(/PLA Basic/)[1]);

    expect(onInventoryPick).toHaveBeenCalledWith(2, null);
    expect(onManualMappingChange).toHaveBeenCalledWith({ 2: 1 });
  });

  it('warns when the inventory has none of the picked colour left', async () => {
    mockPrinter();
    renderPanel({
      inventoryFilaments: [{ ...LAVA_RED, spool_count: 0, remaining_grams: 0 }],
      inventoryPicks: { 2: PICK },
    });

    expect(await screen.findByText(/None of this filament is left in the inventory\./)).toBeInTheDocument();
  });
});

describe('FilamentMapping: a colour from the inventory is always forced (#3649)', () => {
  it('has no force-colour box on the picked slot, and keeps it on the others', async () => {
    mockPrinter();
    renderPanel({
      inventoryPicks: { 2: PICK },
      forceColorMatch: { 1: false, 2: true },
      onForceColorMatchChange: vi.fn(),
    });

    await waitFor(() => expect(screen.getByText('(Waits for filament)')).toBeInTheDocument());
    // Slot 1 is a loaded slot: its box stays.
    expect(screen.getAllByText('Force color match')).toHaveLength(1);
  });

  it('shows the box on both slots without a pick', async () => {
    mockPrinter();
    renderPanel({ forceColorMatch: {}, onForceColorMatchChange: vi.fn() });

    await waitFor(() => expect(screen.getAllByRole('combobox')).toHaveLength(2));
    expect(screen.getAllByText('Force color match')).toHaveLength(2);
  });
});
