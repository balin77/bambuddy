/**
 * The dialogs an entry opens (#3726): set up the slot (printers:control) and
 * a new spool (inventory:create), above the To do panel.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent, render as rtlRender } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { ToastProvider } from '../../contexts/ToastContext';
import { server } from '../mocks/server';
import type { QueueTodoPicture } from '../../api/client';

const granted = new Set(['inventory:update', 'inventory:create', 'printers:control']);

vi.mock('../../contexts/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../contexts/AuthContext')>();
  return {
    ...actual,
    useAuth: () => ({
      user: { id: 1, username: 'op', permissions: [] },
      authEnabled: true,
      loading: false,
      isAdmin: false,
      hasPermission: (p: string) => granted.has(p),
      hasAnyPermission: (...ps: string[]) => ps.some((p) => granted.has(p)),
      canModify: () => true,
    }),
  };
});

const configureProps = vi.fn();
vi.mock('../../components/ConfigureAmsSlotModal', () => ({
  ConfigureAmsSlotModal: (props: Record<string, unknown>) => {
    configureProps(props);
    return <div data-testid="configure-modal" />;
  },
}));
const formProps = vi.fn();
vi.mock('../../components/SpoolFormModal', () => ({
  SpoolFormModal: (props: Record<string, unknown>) => {
    formProps(props);
    return <div data-testid="spool-form-modal" />;
  },
}));

import { PictureActions } from '../../components/QueueTodoSlotActions';

const picture: QueueTodoPicture = {
  printer_id: 7,
  printer_name: 'Shelf X1C',
  compact: false,
  unplaced: [],
  units: [{
    ams_id: 1, ams_type: 1, kind: 'ams', nozzle: 'left', collapsed: false,
    slots: [{
      ams_id: 1, tray_id: 1, is_ht: false, is_external: false, ams_type: 1, type: 'PLA', color: '#C8102E',
      extra_colors: '', effect_type: '', subtype: '', color_name: '', tray_sub_brands: 'PLA Basic', tray_info_idx: 'GFA00',
      remaining_g: 196, remain_percent: null, rfid: false, state: 'out',
      incoming: { filament_index: 0, type: 'PLA', color: '#C8102E', color_name: 'Lava Red', required_g: 505, stock_count: 1 },
    }],
  }],
};

beforeEach(() => {
  vi.clearAllMocks();
  server.use(
    http.get('/api/v1/inventory/spools', () => HttpResponse.json([])),
    http.get('/api/v1/inventory/assignments', () => HttpResponse.json([])),
    http.get('/api/v1/printers/', () => HttpResponse.json([{ id: 7, name: 'Shelf X1C', model: 'X1C' }])),
    http.get('/api/v1/printers/7/status', () => HttpResponse.json({ state: 'IDLE', nozzles: [{ nozzle_diameter: '0.6' }, { nozzle_diameter: '0.4' }], ams_extruder_map: { '1': 1 } })),
  );
});

function renderActions() {
  return rtlRender(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <ToastProvider>
          <PictureActions picture={picture} overlayZIndex="z-[70]" />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('dialogs opened from an entry', () => {
  it('sets the slot up with the slot, its nozzle and diameter, above the panel', async () => {
    renderActions();
    fireEvent.click(await screen.findByRole('button', { name: 'Set up slot B2' }));
    await screen.findByTestId('configure-modal');
    await waitFor(() => expect(configureProps).toHaveBeenLastCalledWith(expect.objectContaining({ nozzleDiameter: '0.4', printerState: 'IDLE' })));
    const props = configureProps.mock.lastCall![0];
    expect(props.printerId).toBe(7);
    expect(props.slotInfo).toMatchObject({ amsId: 1, trayId: 1, trayType: 'PLA', trayColor: 'C8102EFF', extruderId: 1, trayInfoIdx: 'GFA00' });
    expect(props.overlayZIndex).toBe('z-[70]');
    expect(props.printerModel).toBeTruthy();
  });

  it('opens the new-spool form from the picker', async () => {
    renderActions();
    fireEvent.click(await screen.findByRole('button', { name: 'Assign spool for B2' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Add new spool' }));
    await screen.findByTestId('spool-form-modal');
    expect(formProps.mock.lastCall![0]).toMatchObject({ mode: 'create', overlayZIndex: 'z-[70]' });
  });
});
