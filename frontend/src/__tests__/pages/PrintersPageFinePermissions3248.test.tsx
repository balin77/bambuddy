/**
 * Printer card with users holding ONE fine printer permission (#3248):
 * every control follows its own permission, printers:control still opens all.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';

const perms = { held: new Set<string>() };

const mockUseAuth = {
  user: { id: 1, username: 'operator', permissions: [] as string[] },
  authEnabled: true,
  loading: false,
  isAdmin: false,
  login: vi.fn(),
  loginWithToken: vi.fn(),
  logout: vi.fn(),
  refreshAuth: vi.fn(),
  hasPermission: vi.fn((permission: string) => {
    const umbrella = PERMISSION_UMBRELLAS[permission as Permission];
    return perms.held.has(permission) || (umbrella !== undefined && perms.held.has(umbrella));
  }),
  hasAnyPermission: vi.fn(() => true),
  canModify: vi.fn(() => true),
};

vi.mock('../../contexts/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../contexts/AuthContext')>();
  return { ...actual, useAuth: () => mockUseAuth };
});

import { render } from '../utils';
import { PrintersPage } from '../../pages/PrintersPage';
import { PERMISSION_UMBRELLAS } from '../../api/client';
import type { Permission } from '../../api/client';

const PRINTER_ID = 5;

const printerFor = (model: string, extra: Record<string, unknown> = {}) => ({
  id: PRINTER_ID,
  name: `Test ${model}`,
  ip_address: '192.0.2.105',
  serial_number: '00M09A350100005',
  access_code: '12345678',
  model,
  enabled: true,
  nozzle_diameter: 0.4,
  nozzle_type: 'hardened_steel',
  auto_archive: true,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  ...extra,
});

const tray = {
  tray_color: 'FF0000FF',
  tray_type: 'PLA',
  tray_sub_brands: 'PLA Basic',
  tray_id_name: 'A00-R0',
  tray_info_idx: 'GFA00',
  remain: 80,
  k: 0.02,
  cali_idx: null,
  tag_uid: null,
  tray_uuid: null,
  nozzle_temp_min: 190,
  nozzle_temp_max: 230,
  drying_temp: null,
  drying_time: null,
  state: 3,
};

const dryingAms = {
  id: 0,
  humidity: 30,
  temp: 33,
  is_ams_ht: false,
  serial_number: 'AMS00',
  sw_ver: '03.00.21.29',
  dry_sub_status: 0,
  dry_sf_reason: [],
  module_type: 'n3f',
  dry_time: 720,
  dry_status: 2,
  tray: [0, 1, 2, 3].map((id) => ({ id, ...tray })),
};

const statusFor = (state: string, extra: Record<string, unknown> = {}) => ({
  connected: true,
  state,
  progress: state === 'IDLE' ? 0 : 40,
  layer_num: 0,
  total_layers: 0,
  temperatures: { nozzle: 25, bed: 25, chamber: 25 },
  remaining_time: 0,
  filename: state === 'IDLE' ? null : 'part.gcode',
  wifi_signal: -50,
  speed_level: 2,
  chamber_light: false,
  vt_tray: [],
  ams: [],
  ...extra,
});

function setup(model: string, status: Record<string, unknown>, printerExtra: Record<string, unknown> = {}) {
  server.use(
    http.get('/api/v1/printers/', () => HttpResponse.json([printerFor(model, printerExtra)])),
    http.get('/api/v1/queue/', () => HttpResponse.json([])),
    http.get('/api/v1/printers/:id/status', () => HttpResponse.json(status)),
  );
  render(<PrintersPage />);
}

const button = async (name: string) => (await screen.findByRole('button', { name })) as HTMLButtonElement;

describe('PrintersPage with a single fine printer permission (#3248)', () => {
  beforeEach(() => {
    perms.held = new Set();
  });

  it('pause_resume only: Pause is enabled, Stop is not', async () => {
    perms.held = new Set(['printers:pause_resume']);
    setup('X1C', statusFor('RUNNING'));
    expect((await button('Pause')).disabled).toBe(false);
    expect((await button('Stop')).disabled).toBe(true);
  });

  it('stop only: Stop is enabled, Pause is not', async () => {
    perms.held = new Set(['printers:stop']);
    setup('X1C', statusFor('RUNNING'));
    expect((await button('Stop')).disabled).toBe(false);
    expect((await button('Pause')).disabled).toBe(true);
  });

  it('tune only: the chamber light works, Pause and Stop do not', async () => {
    perms.held = new Set(['printers:tune']);
    setup('X1C', statusFor('RUNNING'));
    expect(((await screen.findByTitle('Turn on chamber light')) as HTMLButtonElement).disabled).toBe(false);
    expect((await button('Pause')).disabled).toBe(true);
    expect((await button('Stop')).disabled).toBe(true);
  });

  it('printers:control keeps Pause, Stop and the light', async () => {
    perms.held = new Set(['printers:control']);
    setup('X1C', statusFor('RUNNING'));
    expect((await button('Pause')).disabled).toBe(false);
    expect((await button('Stop')).disabled).toBe(false);
    expect(((await screen.findByTitle('Turn on chamber light')) as HTMLButtonElement).disabled).toBe(false);
  });

  describe('nozzle selector (printers:motion, not tune)', () => {
    const dual = statusFor('IDLE', {
      temperatures: { nozzle: 25, nozzle_2: 25, bed: 25, chamber: 25 },
      active_extruder: 1,
    });

    it('motion only: the selector opens', async () => {
      perms.held = new Set(['printers:motion']);
      setup('H2D', dual, { nozzle_count: 2 });
      fireEvent.click(await screen.findByTitle(/^Active: /));
      expect(await screen.findByText('Set Nozzle Selection')).toBeTruthy();
    });

    it('tune only: the selector stays closed', async () => {
      perms.held = new Set(['printers:tune']);
      setup('H2D', dual, { nozzle_count: 2 });
      // The chamber light proves the card is rendered and tune is honoured.
      expect(((await screen.findByTitle('Turn on chamber light')) as HTMLButtonElement).disabled).toBe(false);
      expect(screen.queryByTitle(/^Active: /)).toBeNull();
      expect(screen.queryByText('Set Nozzle Selection')).toBeNull();
    });
  });

  describe('drying stop button (printers:drying)', () => {
    const drying = statusFor('IDLE', { supports_drying: true, drying_screen_only: false, ams: [dryingAms] });

    it('drying only: Stop Drying sends drying/stop', async () => {
      perms.held = new Set(['printers:drying']);
      const sent: string[] = [];
      server.use(
        http.post('/api/v1/printers/:id/drying/stop', ({ request }) => {
          sent.push(new URL(request.url).pathname);
          return HttpResponse.json({ status: 'drying_stopped', ams_id: 0 });
        }),
      );
      setup('X1C', drying);
      const stops = await screen.findAllByTitle('Stop Drying');
      expect((stops[0] as HTMLButtonElement).disabled).toBe(false);
      await userEvent.setup().click(stops[0]);
      await waitFor(() => expect(sent).toEqual([`/api/v1/printers/${PRINTER_ID}/drying/stop`]));
    });

    it('motion only: no usable Stop Drying button', async () => {
      perms.held = new Set(['printers:motion']);
      setup('X1C', drying);
      await screen.findByText('Test X1C');
      await waitFor(() => expect(screen.getAllByTitle('You do not have permission to control printers').length).toBeGreaterThan(0));
      expect(screen.queryAllByTitle('Stop Drying')).toEqual([]);
    });
  });

  describe('card menu Reconnect (printers:admin)', () => {
    const openMenu = async () => {
      await screen.findByText('Test X1C');
      const trigger = (await screen.findAllByTitle(/more/i)).find((el) => el.tagName === 'BUTTON');
      fireEvent.click(trigger!);
      return (await screen.findByRole('button', { name: 'Reconnect' })) as HTMLButtonElement;
    };

    it('admin only: Reconnect is enabled', async () => {
      perms.held = new Set(['printers:admin']);
      setup('X1C', statusFor('IDLE'));
      const item = await openMenu();
      expect(item.disabled).toBe(false);
      expect(item).toHaveClass('hover:bg-bambu-dark-tertiary');
    });

    it('pause_resume only: Reconnect is disabled and has no hover highlight', async () => {
      perms.held = new Set(['printers:pause_resume']);
      setup('X1C', statusFor('IDLE'));
      const item = await openMenu();
      expect(item.disabled).toBe(true);
      expect(item).not.toHaveClass('hover:bg-bambu-dark-tertiary');
    });
  });
});
