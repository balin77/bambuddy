/**
 * The "Printer idle: waiting for filament" channel toggle (#3725): on provider
 * cards, on by default, saved under its own field.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { NotificationProviderCard } from '../../components/NotificationProviderCard';
import type { NotificationProvider } from '../../api/client';

afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
});

function buildProvider(overrides: Partial<NotificationProvider> = {}): NotificationProvider {
  return {
    id: 1,
    name: 'My ntfy',
    provider_type: 'ntfy',
    enabled: true,
    config: { server: 'https://ntfy.sh', topic: 'bambuddy' },
    on_print_start: false,
    on_print_complete: false,
    on_print_failed: false,
    on_print_stopped: false,
    on_print_progress: false,
    on_print_missing_spool_assignment: false,
    on_printer_offline: false,
    on_printer_error: false,
    on_ai_failure_detection: false,
    on_filament_low: false,
    on_maintenance_due: false,
    on_ams_humidity_high: false,
    on_ams_temperature_high: false,
    on_ams_ht_humidity_high: false,
    on_ams_ht_temperature_high: false,
    on_plate_not_empty: false,
    on_bed_cooled: false,
    on_first_layer_complete: false,
    on_print_pause_upcoming: false,
    on_queue_job_added: false,
    on_queue_job_assigned: false,
    on_queue_job_started: false,
    on_queue_job_waiting: false,
    on_printer_idle_for_filament: true,
    on_queue_job_skipped: false,
    on_queue_job_failed: false,
    on_queue_completed: false,
    on_stock_reorder_alert: false,
    on_stock_break_alert: false,
    quiet_hours_enabled: false,
    quiet_hours_start: null,
    quiet_hours_end: null,
    daily_digest_enabled: false,
    daily_digest_time: null,
    printer_id: null,
    last_success: null,
    last_error: null,
    last_error_at: null,
    created_at: '2026-11-24T00:00:00Z',
    updated_at: '2026-11-24T00:00:00Z',
    ...overrides,
  };
}

async function idleSwitch(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByText(/event settings/i));
  const row = (await screen.findByText('Printer Idle: Waiting for Filament')).closest('div.flex')!;
  return within(row as HTMLElement).getByRole('switch');
}

describe('NotificationProviderCard - Printer idle: waiting for filament', () => {
  it('shows the switch on for a provider that has it on', async () => {
    const user = userEvent.setup();
    render(<NotificationProviderCard provider={buildProvider()} onEdit={vi.fn()} />);

    expect(await idleSwitch(user)).toHaveAttribute('aria-checked', 'true');
  });

  it('shows the switch off for a provider that has it off', async () => {
    const user = userEvent.setup();
    render(<NotificationProviderCard provider={buildProvider({ on_printer_idle_for_filament: false })} onEdit={vi.fn()} />);

    expect(await idleSwitch(user)).toHaveAttribute('aria-checked', 'false');
  });

  it('reads a provider the server sent without the field as on', async () => {
    const user = userEvent.setup();
    const provider = buildProvider() as Partial<NotificationProvider>;
    delete provider.on_printer_idle_for_filament;
    render(<NotificationProviderCard provider={provider as NotificationProvider} onEdit={vi.fn()} />);

    expect(await idleSwitch(user)).toHaveAttribute('aria-checked', 'true');
  });

  it('PATCHes on_printer_idle_for_filament when toggled', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.patch('*/api/v1/notifications/1', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(buildProvider({ on_printer_idle_for_filament: false }));
      }),
    );
    const user = userEvent.setup();
    render(<NotificationProviderCard provider={buildProvider()} onEdit={vi.fn()} />);

    await user.click(await idleSwitch(user));

    await waitFor(() => expect(captured).toEqual({ on_printer_idle_for_filament: false }));
  });
});
