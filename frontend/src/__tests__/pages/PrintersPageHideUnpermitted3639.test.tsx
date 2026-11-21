/**
 * Hiding the controls a user cannot use on the printer page (#3639).
 *
 * Without the groups' option a control the user may not use is greyed out, as
 * always. With it the control is left out, and so is a section left with none.
 * A control disabled for another reason (offline, nothing printing) stays.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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

function setup(statusExtra: Record<string, unknown> = {}, printers: unknown[] = [printer]) {
  server.use(
    http.get('/api/v1/printers/', () => HttpResponse.json(printers)),
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
      auth.granted = new Set(['printers:read', 'printers:tune', 'printers:stop', 'printers:clear_plate']);
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

  describe('option on: what is left of a section, and what stays', () => {
    beforeEach(() => {
      auth.hide = true;
    });

    it('leaves out the add button of the empty state and the toolbar action group with its divider', async () => {
      setup({}, []);
      expect(await screen.findByText('No printers configured yet')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Add Printer/ })).toBeNull();
      // Filter and view groups only: two dividers, none for the empty action group
      expect(document.querySelectorAll('.h-6.w-px').length).toBe(2);
    });

    it('draws the third toolbar divider and the add button when the option is off', async () => {
      auth.hide = false;
      setup({}, []);
      expect(await screen.findByText('No printers configured yet')).toBeInTheDocument();
      expect(screen.getAllByRole('button', { name: /Add Printer/ }).length).toBe(2);
      expect(document.querySelectorAll('.h-6.w-px').length).toBe(3);
    });

    describe('compact toolbar', () => {
      const proto = HTMLElement.prototype;
      const elProto = Element.prototype;
      let offsetDesc: PropertyDescriptor | undefined;
      let clientDesc: PropertyDescriptor | undefined;
      beforeEach(() => {
        offsetDesc = Object.getOwnPropertyDescriptor(proto, 'offsetWidth');
        clientDesc = Object.getOwnPropertyDescriptor(elProto, 'clientWidth');
        Object.defineProperty(proto, 'offsetWidth', { configurable: true, get: () => 800 });
        Object.defineProperty(elProto, 'clientWidth', { configurable: true, get: () => 300 });
      });
      afterEach(() => {
        if (offsetDesc) Object.defineProperty(proto, 'offsetWidth', offsetDesc);
        if (clientDesc) Object.defineProperty(elProto, 'clientWidth', clientDesc);
      });

      it('has no Actions menu when the user has no action to offer', async () => {
        setup();
        await waitForBed();
        expect(await screen.findByRole('button', { name: 'Filters' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'View' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Actions' })).toBeNull();
      });

      it('keeps the Actions menu without the option', async () => {
        auth.hide = false;
        setup();
        await waitForBed();
        expect(await screen.findByRole('button', { name: 'Actions' })).toBeInTheDocument();
      });
    });

    it('keeps plate detection for a user with only printers:update, and leaves no right-hand group', async () => {
      auth.granted = new Set(['printers:read', 'printers:update']);
      setup();
      await waitForBed();

      expect(screen.getByText('Controls')).toBeInTheDocument();
      expect(screen.getByTitle('Plate check disabled - Click to enable')).toBeEnabled();
      expect(screen.queryByTitle(LIGHT)).toBeNull();
      expect(screen.queryByTestId('speed-control')).toBeNull();
      expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Stop' })).toBeNull();
      // The print buttons' group is not drawn at all, so it reserves no gap
      expect(document.querySelector('.ml-auto.flex.items-center.justify-end.gap-2.flex-shrink-0')).toBeNull();
    });

    it('opens the HMS dialog from the card with no Clear button', async () => {
      setup({
        hms_errors: [{ attr: 0x0300, code: '0x400C', severity: 1, description: 'The task was canceled.' }],
      });
      await waitForBed();
      fireEvent.click(await screen.findByTitle('Click to view HMS errors'));

      expect(await screen.findByText('The task was canceled.')).toBeInTheDocument();
      expect(screen.queryByText('Clear Errors')).toBeNull();
    });

    it('offers Print only with both library:upload and queue:create', async () => {
      auth.granted = new Set(['printers:read', 'library:upload']);
      setup();
      await waitForBed();
      expect(screen.queryByRole('button', { name: /^Print$/ })).toBeNull();
    });

    it('hides Print with queue:create alone', async () => {
      auth.granted = new Set(['printers:read', 'queue:create']);
      setup();
      await waitForBed();
      expect(screen.queryByRole('button', { name: /^Print$/ })).toBeNull();
    });

    it('shows Print with both', async () => {
      auth.granted = new Set(['printers:read', 'library:upload', 'queue:create']);
      setup();
      await waitForBed();
      expect(screen.getByRole('button', { name: /^Print$/ })).toBeEnabled();
    });

    it('keeps a readout tile clickable for a user who may tune the printer', async () => {
      auth.granted = new Set(['printers:read', 'printers:tune']);
      setup();
      const bed = (await screen.findByText('Bed')).parentElement!;
      expect(bed.className).toContain('cursor-pointer');
      expect(bed.className).not.toContain('cursor-default');
    });
  });

  describe('skip-objects badge', () => {
    const printing = {
      state: 'RUNNING',
      current_print: 'plate.3mf',
      subtask_name: 'plate',
      progress: 40,
      printable_objects_count: 3,
    };
    const objects = () =>
      http.get('/api/v1/printers/:id/print/objects', () =>
        HttpResponse.json({ objects: [], total: 3, skipped_count: 2, is_printing: true, bbox_all: null }),
      );

    it('keeps the skipped count as a plain readout and reserves no space for the button when it is hidden', async () => {
      auth.hide = true;
      server.use(objects());
      setup(printing);
      const readout = await screen.findByTestId('skipped-count-readout');
      expect(readout.textContent).toBe('2');
      expect(readout.closest('button')).toBeNull();
      expect(document.querySelector('p.pr-8.text-sm')).toBeNull();
      expect(document.querySelector('div.pr-8.items-center')).toBeNull();
    });

    it('keeps the button and its reserved space with the permission', async () => {
      auth.hide = true;
      auth.granted = new Set(['printers:read', 'printers:stop']);
      server.use(objects());
      setup(printing);
      expect(await screen.findByText('2')).toBeInTheDocument();
      expect(screen.queryByTestId('skipped-count-readout')).toBeNull();
      expect(document.querySelector('p.pr-8.text-sm')).not.toBeNull();
    });

    it('reserves the space without the option', async () => {
      server.use(objects());
      setup(printing);
      await waitForBed();
      expect(document.querySelector('p.pr-8.text-sm')).not.toBeNull();
    });
  });

  describe('firmware dialog', () => {
    const firmware = {
      printer_id: 4,
      printer_name: 'Farm X1C',
      model: 'X1C',
      current_version: '01.08.00.00',
      latest_version: '01.09.00.00',
      update_available: true,
      download_url: 'https://example.com/firmware.bin',
      release_notes: 'New features added.',
      available_versions: [
        { version: '01.09.00.00', file_available: true, download_url: null, release_notes: null, release_time: null },
        { version: '01.08.00.00', file_available: true, download_url: null, release_notes: null, release_time: null },
      ],
    };

    const openDialog = async () => {
      auth.granted.add('firmware:read');
      server.use(
        http.get('/api/v1/firmware/updates/:id', () => HttpResponse.json(firmware)),
        http.get('/api/v1/settings/', () =>
          HttpResponse.json({ check_printer_firmware: true, auto_archive: true, save_thumbnails: true }),
        ),
      );
      setup();
      const badge = await screen.findAllByText('01.08.00.00');
      fireEvent.click(badge[0].closest('button')!);
      expect(await screen.findByText('Firmware Update')).toBeInTheDocument();
    };

    it('leaves out the version list without firmware:update, and keeps the current version', async () => {
      auth.hide = true;
      await openDialog();
      expect(screen.getByText('Current:')).toBeInTheDocument();
      expect(screen.queryByText('Available versions')).toBeNull();
    });

    it('lists the versions, disabled, without the option', async () => {
      auth.hide = false;
      await openDialog();
      expect(screen.getByText('Available versions')).toBeInTheDocument();
    });

    it('lists the versions with firmware:update', async () => {
      auth.hide = true;
      auth.granted = new Set(['printers:read', 'firmware:update']);
      await openDialog();
      expect(screen.getByText('Available versions')).toBeInTheDocument();
    });
  });

  describe('farm: the fine printer permissions (#3248)', () => {
    const emptyChanger = { ...printer, plate_capacity: 5, plates_remaining: 0 };
    const REFILL = 'Refilled / Emptied';
    const scheduledRow = {
      id: 1,
      printer_id: 4,
      ams_id: 0,
      temp: 45,
      duration_hours: 12,
      filament: 'PLA',
      rotate_tray: false,
      start_after: '2026-07-25T23:24:00',
      status: 'pending',
      waiting_reason: null,
      error_message: null,
      created_at: '2026-07-25T20:00:00',
      started_at: null,
      completed_at: null,
    };

    beforeEach(() => {
      auth.hide = true;
    });

    it('a helper with pause/resume and clear plate sees Pause and no Stop, and no left-hand controls', async () => {
      auth.granted = new Set(['printers:read', 'printers:pause_resume', 'printers:clear_plate']);
      setup({ awaiting_plate_clear: true });
      await waitForBed();

      expect(screen.getByText('Controls')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Pause' })).toBeDisabled();
      expect(screen.queryByRole('button', { name: 'Stop' })).toBeNull();
      expect(screen.queryByTitle(LIGHT)).toBeNull();
      expect(screen.queryByTestId('speed-control')).toBeNull();
      expect(screen.getByRole('button', { name: CLEAR_PLATE })).toBeEnabled();
      // Reconnect needs printers:admin, Edit and Delete their own rights
      fireEvent.click(screen.getByTitle(/more/i));
      expect(await screen.findByText('Printer Information')).toBeInTheDocument();
      expect(screen.queryByText('Reconnect')).toBeNull();
      expect(screen.queryByText('Delete')).toBeNull();
    });

    it('a helper with only stop gets the Stop group and no Pause', async () => {
      auth.granted = new Set(['printers:read', 'printers:stop']);
      setup();
      await waitForBed();

      expect(screen.getByRole('button', { name: 'Stop' })).toBeDisabled();
      expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull();
    });

    it('a helper with only tune gets the left-hand tiles and no print buttons', async () => {
      auth.granted = new Set(['printers:read', 'printers:tune']);
      setup();
      await waitForBed();

      expect(screen.getByText('Controls')).toBeInTheDocument();
      expect(screen.getByTitle(LIGHT)).toBeEnabled();
      expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Stop' })).toBeNull();
    });

    it('leaves out the Refill button of an empty plate changer without clear plate, and keeps the count', async () => {
      auth.granted = new Set(['printers:read']);
      setup({}, [emptyChanger]);
      await waitForBed();

      expect(screen.queryByRole('button', { name: REFILL })).toBeNull();
      // The chip stays as a read-only count
      expect(screen.getAllByText('0/5').length).toBeGreaterThan(0);
      expect(screen.queryAllByRole('button').filter((b) => b.textContent?.includes('0/5'))).toHaveLength(0);
    });

    it('keeps the Refill button with clear plate, and greyed out without the option', async () => {
      auth.granted = new Set(['printers:read', 'printers:clear_plate']);
      setup({}, [emptyChanger]);
      await waitForBed();
      expect(screen.getByRole('button', { name: REFILL })).toBeEnabled();
    });

    it('greys the Refill button out when the option is off', async () => {
      auth.hide = false;
      auth.granted = new Set(['printers:read']);
      setup({}, [emptyChanger]);
      await waitForBed();
      expect(screen.getByRole('button', { name: REFILL })).toBeDisabled();
    });

    it('the scheduled-drying banner has no cancel button without printers:drying', async () => {
      auth.granted = new Set(['printers:read']);
      server.use(http.get('/api/v1/scheduled-dryings', () => HttpResponse.json([scheduledRow])));
      setup();
      await screen.findByTestId('scheduled-drying-pending');
      expect(screen.queryByTitle('Cancel scheduled drying')).toBeNull();
      expect(screen.queryByTitle(NO_CONTROL)).toBeNull();
    });

    it('the scheduled-drying banner keeps its cancel button with printers:drying, and greyed without the option', async () => {
      auth.granted = new Set(['printers:read', 'printers:drying']);
      server.use(http.get('/api/v1/scheduled-dryings', () => HttpResponse.json([scheduledRow])));
      setup();
      await screen.findByTestId('scheduled-drying-pending');
      expect(screen.getByTitle('Cancel scheduled drying')).toBeEnabled();
    });

    it('the scheduled-drying cancel button is greyed out when the option is off', async () => {
      auth.hide = false;
      auth.granted = new Set(['printers:read']);
      server.use(http.get('/api/v1/scheduled-dryings', () => HttpResponse.json([scheduledRow])));
      setup();
      const banner = await screen.findByTestId('scheduled-drying-pending');
      expect(within(banner).getByTitle(NO_CONTROL)).toBeDisabled();
    });

    it('offers bulk select to a user with any of the four printer rights', async () => {
      auth.granted = new Set(['printers:read', 'printers:maintenance']);
      setup();
      await waitForBed();
      expect(screen.getByTitle('Select')).toBeInTheDocument();
    });
  });

  it('shows the toolbar actions, disabled, without the option', async () => {
    setup();
    await waitForBed();
    expect(screen.getByRole('button', { name: /Add Printer/ })).toBeDisabled();
  });
});
