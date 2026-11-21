/**
 * Hiding the controls a user cannot use on the printer page (#3639).
 *
 * Without the groups' option a control the user may not use is greyed out, as
 * always. With it the control is left out, and so is a section left with none.
 * A control disabled for another reason (offline, nothing printing) stays.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';

const auth = { granted: new Set<string>(), hide: false };

vi.mock('../../contexts/AuthContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../contexts/AuthContext')>();
  return {
    ...actual,
    useAuth: () => ({
      user: { id: 1, username: 'helper', permissions: [] as string[] },
      authEnabled: true,
      loading: false,
      isAdmin: false,
      hideUnpermitted: auth.hide,
      login: vi.fn(),
      loginWithToken: vi.fn(),
      logout: vi.fn(),
      refreshAuth: vi.fn(),
      hasPermission: (permission: string) => auth.granted.has(permission),
      hasAnyPermission: (...permissions: string[]) => permissions.some((p) => auth.granted.has(p)),
      canModify: () => false,
    }),
  };
});

import { render } from '../utils';
import { PrintersPage } from '../../pages/PrintersPage';

const printer = {
  id: 4,
  name: 'Farm X1C',
  ip_address: '192.0.2.104',
  serial_number: '00M09A350100004',
  access_code: '12345678',
  model: 'X1C',
  enabled: true,
  nozzle_diameter: 0.4,
  nozzle_type: 'hardened_steel',
  auto_archive: true,
  require_plate_clear: true,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

const baseTray = {
  tray_color: 'FF0000FF',
  tray_type: 'PLA',
  tray_sub_brands: 'PLA Basic',
  tray_id_name: '',
  tray_info_idx: 'GFL99',
  remain: 80,
  k: 0.02,
  cali_idx: null,
  tag_uid: null,
  tray_uuid: null,
  nozzle_temp_min: 190,
  nozzle_temp_max: 230,
  drying_temp: null,
  drying_time: null,
  state: 11,
};

const status = (extra: Record<string, unknown> = {}) => ({
  connected: true,
  state: 'IDLE',
  progress: 0,
  layer_num: 0,
  total_layers: 0,
  temperatures: { nozzle: 25, bed: 25, chamber: 25 },
  remaining_time: 0,
  filename: null,
  wifi_signal: -50,
  speed_level: 2,
  chamber_light: false,
  cooling_fan_speed: 0,
  big_fan1_speed: 0,
  big_fan2_speed: 0,
  vt_tray: [],
  ams: [],
  awaiting_plate_clear: false,
  ...extra,
});

function setup(statusExtra: Record<string, unknown> = {}) {
  server.use(
    http.get('/api/v1/printers/', () => HttpResponse.json([printer])),
    http.get('/api/v1/queue/', () => HttpResponse.json([])),
    http.get('/api/v1/printers/:id/status', () => HttpResponse.json(status(statusExtra))),
  );
  render(<PrintersPage />);
}

const CLEAR_PLATE = 'Mark plate as cleared';
const LIGHT = 'Turn on chamber light';
const NO_UPDATE = 'You do not have permission to update printers';
const NO_FILES = 'You do not have permission to access printer files';
const NO_CAMERA = 'You do not have permission to view cameras';
const NO_CONTROL = 'You do not have permission to control printers';

/** Wait until the card is drawn. */
const cardReady = () => screen.findByText('Farm X1C');
const waitForBed = async () => expect(await screen.findByText('Bed')).toBeInTheDocument();

describe('PrintersPage hides controls a restricted user cannot use (#3639)', () => {
  beforeEach(() => {
    auth.granted = new Set(['printers:read']);
    auth.hide = false;
  });

  describe('option off: greyed out, as before', () => {
    it('keeps every control and disables the ones without permission', async () => {
      setup({ awaiting_plate_clear: true });
      await waitForBed();

      expect(screen.getByText('Controls')).toBeInTheDocument();
      // Light, airduct-free X1C jog and the rest of the controls: present, all disabled
      const noControl = screen.getAllByTitle(NO_CONTROL).filter((el) => el.tagName === 'BUTTON');
      expect(noControl.length).toBeGreaterThanOrEqual(3);
      noControl.forEach((el) => expect(el).toBeDisabled());
      expect(screen.getByTestId('speed-control')).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Stop' })).toBeDisabled();
      expect(screen.getByRole('button', { name: CLEAR_PLATE })).toBeDisabled();
      expect(screen.getByRole('button', { name: /^Print$/ })).toBeDisabled();
      expect(screen.getAllByTitle(NO_UPDATE).length).toBeGreaterThan(0);
      expect(screen.getByTitle(NO_FILES)).toBeDisabled();
      expect(screen.getAllByTitle(NO_CAMERA).length).toBeGreaterThan(0);
    });

    it('draws the AMS slot actions disabled', async () => {
      setup({ ams: [], vt_tray: [{ id: 254, ...baseTray }] });
      await waitFor(() => expect(screen.getAllByTestId('filament-slot').length).toBeGreaterThan(0));
      fireEvent.mouseEnter(screen.getAllByTestId('filament-slot')[0]);
      expect(await screen.findByRole('button', { name: 'Load' })).toBeDisabled();
    });
  });

  describe('option on', () => {
    beforeEach(() => {
      auth.hide = true;
    });

    it('leaves out every control the user lacks the permission for, and the empty Controls section', async () => {
      setup({ awaiting_plate_clear: true });
      await waitForBed();

      expect(screen.queryByText('Controls')).toBeNull();
      expect(screen.queryByTitle(LIGHT)).toBeNull();
      expect(screen.queryByTitle(NO_CONTROL)).toBeNull();
      expect(screen.queryByTestId('speed-control')).toBeNull();
      expect(screen.queryByRole('button', { name: 'Stop' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull();
      expect(screen.queryByRole('button', { name: CLEAR_PLATE })).toBeNull();
      expect(screen.queryByRole('button', { name: /^Print$/ })).toBeNull();
      expect(screen.queryByTitle(NO_FILES)).toBeNull();
      expect(screen.queryByTitle(NO_CAMERA)).toBeNull();
    });

    it('keeps the readings, and the card menu with the entries that need no permission', async () => {
      setup();
      await waitForBed();

      expect(screen.getByText('Bed')).toBeInTheDocument();
      fireEvent.click(screen.getByTitle(/more/i));
      expect(await screen.findByText('Printer Information')).toBeInTheDocument();
      expect(screen.queryByText('Edit')).toBeNull();
      expect(screen.queryByText('Delete')).toBeNull();
      expect(screen.queryByText('Enter maintenance mode')).toBeNull();
    });

    it('shows a readout without the "no permission" dimming', async () => {
      setup();
      const bed = (await screen.findByText('Bed')).parentElement!;
      expect(bed.className).not.toContain('opacity-80');
      expect(bed).not.toHaveAttribute('title', NO_CONTROL);
    });

    it('shows the controls the user does have, and keeps one that is disabled for another reason', async () => {
      auth.granted = new Set(['printers:read', 'printers:control', 'printers:clear_plate']);
      setup({ awaiting_plate_clear: true });
      await waitForBed();

      expect(screen.getByText('Controls')).toBeInTheDocument();
      expect(screen.getByTitle(LIGHT)).toBeEnabled();
      // Nothing is printing: Stop stays, greyed, instead of vanishing.
      expect(screen.getByRole('button', { name: 'Stop' })).toBeDisabled();
      expect(screen.getByRole('button', { name: CLEAR_PLATE })).toBeEnabled();
      // printers:update is missing: plate detection, which needs it, is gone
      expect(screen.queryByTitle(NO_UPDATE)).toBeNull();
    });

    it('keeps a control the user may use on an offline printer, greyed', async () => {
      auth.granted = new Set(['printers:read', 'camera:view', 'printers:files']);
      setup({ connected: false });
      await cardReady();

      // Offline is not a missing permission: the camera button stays, disabled.
      const camera = await screen.findByTitle(/^Open camera/);
      expect(camera).toBeDisabled();
      expect(screen.getByTitle('Browse printer files')).toBeEnabled();
      expect(screen.queryByTitle(NO_CAMERA)).toBeNull();
    });

    it('leaves the AMS slot menu without a box when it has no action', async () => {
      setup({ vt_tray: [{ id: 254, ...baseTray }] });
      await waitFor(() => expect(screen.getAllByTestId('filament-slot').length).toBeGreaterThan(0));
      fireEvent.mouseEnter(screen.getAllByTestId('filament-slot')[0]);

      // The hover card is portaled to the body as a fixed layer.
      const card = await waitFor(() => {
        const el = document.body.querySelector<HTMLElement>(':scope > .fixed.z-\\[60\\]');
        expect(el).not.toBeNull();
        return el!;
      });
      expect(card.textContent).toContain('PLA');
      expect(within(card).queryByRole('button', { name: 'Load' })).toBeNull();
      expect(within(card).queryByRole('button', { name: 'Unload' })).toBeNull();
      expect(card.querySelector('.border-t.space-y-1')).toBeNull();
    });

    it('leaves out the page toolbar actions and the empty-state button', async () => {
      setup();
      await waitForBed();
      expect(screen.queryByTitle('Select')).toBeNull();
      expect(screen.queryByRole('button', { name: /Add Printer/ })).toBeNull();
    });
  });

  it('shows the toolbar actions, disabled, without the option', async () => {
    setup();
    await waitForBed();
    expect(screen.getByRole('button', { name: /Add Printer/ })).toBeDisabled();
  });
});
