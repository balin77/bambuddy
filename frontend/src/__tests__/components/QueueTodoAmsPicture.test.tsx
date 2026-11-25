/**
 * The AMS picture of the To do list (#3726): each filament to load stands in
 * the column of its slot, states are told in words, units nothing goes into
 * are folded, a model job's printers can be switched.
 */
import { describe, it, expect, vi } from 'vitest';
import { screen, within, fireEvent } from '@testing-library/react';
import { render } from '../utils';
import type {
  QueueTodo,
  QueueTodoFilament,
  QueueTodoPicture,
  QueueTodoPictureSlot,
  QueueTodoPictureUnit,
} from '../../api/client';

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

import { AmsPicture, AmsPictures } from '../../components/QueueTodoAmsPicture';
import { QueueTodoList } from '../../components/QueueTodoList';

function slot(trayId: number, overrides: Partial<QueueTodoPictureSlot> = {}): QueueTodoPictureSlot {
  return {
    ams_id: 0,
    tray_id: trayId,
    is_ht: false,
    is_external: false,
    ams_type: 1,
    type: 'PLA',
    color: '#C9B79C',
    extra_colors: '',
    effect_type: '',
    subtype: '',
    color_name: '',
    tray_sub_brands: '',
    tray_info_idx: '',
    remaining_g: null,
    remain_percent: null,
    rfid: false,
    state: 'keep',
    incoming: null,
    ...overrides,
  };
}

function unit(slots: QueueTodoPictureSlot[], overrides: Partial<QueueTodoPictureUnit> = {}): QueueTodoPictureUnit {
  return { ams_id: 0, ams_type: 1, kind: 'ams', nozzle: null, collapsed: false, slots, ...overrides };
}

function picture(units: QueueTodoPictureUnit[], overrides: Partial<QueueTodoPicture> = {}): QueueTodoPicture {
  return { printer_id: 1, printer_name: 'Shelf P1S right', compact: false, units, unplaced: [], ...overrides };
}

const lavaRed: QueueTodoFilament = {
  type: 'PLA', color: '#C8102E', color_name: 'Lava Red', no_stock: false, short: true, required_g: 505,
  short_trays: [{ ams_id: 0, tray_id: 2, remaining_grams: 196 }],
};
const incoming = (index: number, overrides = {}) => ({
  filament_index: index, type: 'PLA', color: '#C8102E', color_name: 'Lava Red', required_g: 505, stock_count: null, ...overrides,
});

const replaceA3 = picture([
  unit([
    slot(0, { color_name: 'Cotton White', color: '#F4EFEB', remaining_g: 227 }),
    slot(1, { color_name: 'Army Beige', remaining_g: 640 }),
    slot(2, { color: '#C8102E', color_name: 'Lava Red', remaining_g: 196, state: 'out', incoming: incoming(0) }),
    slot(3, { type: '', color: '', state: 'empty' }),
  ]),
]);

describe('AmsPicture', () => {
  it('puts the incoming filament and its arrow in the column of its slot and an empty cell above the others', () => {
    render(<AmsPicture picture={replaceA3} filaments={[lavaRed]} />);
    const card = screen.getByTestId('todo-ams-incoming');
    expect(card).toHaveStyle({ gridColumn: '3', gridRow: '1' });
    expect(screen.getByTestId('todo-ams-arrow')).toHaveStyle({ gridColumn: '3', gridRow: '2' });
    expect(within(screen.getByTestId('todo-ams-arrow')).getByRole('img', { name: 'goes into slot A3' })).toBeInTheDocument();
    const slots = screen.getAllByTestId('todo-ams-slot');
    expect(slots.map((s) => s.style.gridColumn)).toEqual(['1', '2', '3', '4']);
    expect(slots.every((s) => s.style.gridRow === '3')).toBe(true);
    // One empty cell above each of the three slots nothing goes into.
    const cells = screen.getAllByTestId('todo-ams-empty-cell');
    expect(cells.map((c) => c.style.gridColumn)).toEqual(['1', '2', '4']);
    // One grid with four equal columns, no wider than the mockup's on a desktop.
    expect(screen.getByTestId('todo-ams-grid')).toHaveStyle({ gridTemplateColumns: 'repeat(4, minmax(0, 7.5rem))' });
  });

  it('says what a new spool is: at least the grams of a short one, stock for a missing one', () => {
    const two = picture([
      unit([
        slot(0, { type: '', color: '', state: 'empty', incoming: incoming(0, { color: '#FF69B4', color_name: 'Pink', stock_count: 2 }) }),
        slot(1, { type: '', color: '', state: 'empty', incoming: incoming(1, { color: '#00FF00', color_name: 'Green', stock_count: 0 }) }),
      ]),
    ]);
    const fils: QueueTodoFilament[] = [
      { type: 'PLA', color: '#FF69B4', color_name: 'Pink', no_stock: false },
      { type: 'PLA', color: '#00FF00', color_name: 'Green', no_stock: false },
    ];
    render(<AmsPicture picture={two} filaments={fils} />);
    const cards = screen.getAllByTestId('todo-ams-incoming');
    expect(cards[0]).toHaveTextContent('in stock: 2 spools');
    expect(cards[1]).toHaveTextContent('not in stock');
    const { unmount } = render(<AmsPicture picture={replaceA3} filaments={[lavaRed]} />);
    expect(screen.getAllByTestId('todo-ams-incoming').at(-1)).toHaveTextContent('new, at least 505 g');
    unmount();
  });

  it('tells every state in words, never by colour alone', () => {
    const states = picture([
      unit([
        slot(0, { state: 'locked', remaining_g: 80 }),
        slot(1, { state: 'out', remaining_g: 90 }),
        slot(2, { state: 'fits', remaining_g: 227 }),
        slot(3, { type: '', color: '', state: 'empty' }),
      ]),
      unit([slot(0, { type: '', color: '', state: 'unknown' }), slot(1, { remain_percent: 80 }), slot(2)], { ams_id: 1 }),
    ]);
    render(<AmsPicture picture={states} filaments={[]} />);
    const text = screen.getAllByTestId('todo-ams-slot').map((s) => [s.dataset.state, (s.textContent ?? '').replace(/\u00a0/g, ' ')]);
    expect(text[0][1]).toContain('printing now');
    expect(text[1][1]).toContain('90 g · out');
    expect(text[2][1]).toContain('fits · 227 g');
    expect(text[3][1]).toContain('empty');
    expect(text[4][1]).toContain('unknown');
    expect(text[5][1]).toContain('80%');
    // Amount not known: a dash, no invented number.
    expect(text[6][1]).toContain('—');
    expect(screen.getByRole('img', { name: /Locked: the running print uses this slot/ })).toBeInTheDocument();
  });

  it('folds the units nothing goes into behind a toggle that is a real button', () => {
    const two = picture([
      unit([slot(0), slot(1)], { ams_id: 0, collapsed: true }),
      unit([slot(0, { type: '', color: '', state: 'empty', incoming: incoming(0) }), slot(1)], { ams_id: 1 }),
    ]);
    render(<AmsPicture picture={two} filaments={[lavaRed]} />);
    expect(screen.getAllByTestId('todo-ams-unit')).toHaveLength(1);
    const toggle = screen.getByRole('button', { name: 'Show AMS-A' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle.className).toContain('min-h-[44px]');
    fireEvent.click(toggle);
    expect(screen.getAllByTestId('todo-ams-unit')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Hide AMS-A' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('names the nozzle of a unit on a dual-nozzle printer', () => {
    const dual = picture([unit([slot(0)], { ams_id: 1, nozzle: 'left' }), unit([slot(0)], { ams_id: 0, nozzle: 'right' })]);
    render(<AmsPicture picture={dual} filaments={[]} />);
    expect(screen.getByRole('region', { name: 'AMS-B · Left nozzle' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'AMS-A · Right nozzle' })).toBeInTheDocument();
  });

  it('joins AMS-HT units into one row with their own labels, and the external holder is its own unit', () => {
    const ht = (id: number) => unit([slot(0, { ams_id: id, is_ht: true, ams_type: 4 })], { ams_id: id, ams_type: 4, kind: 'ht' });
    const ext = unit([slot(0, { ams_id: 255, is_external: true, ams_type: null })], { ams_id: 255, ams_type: null, kind: 'external' });
    render(<AmsPicture picture={picture([ht(128), ht(129), ext])} filaments={[]} />);
    const units = screen.getAllByTestId('todo-ams-unit');
    expect(units).toHaveLength(2);
    expect(within(units[0]).getAllByTestId('todo-ams-slot').map((s) => s.textContent?.slice(0, 4))).toEqual(['HT-A', 'HT-B']);
    expect(within(units[1]).getByTestId('todo-ams-slot')).toHaveTextContent('Ext');
    expect(units[1]).toHaveAccessibleName('External spool');
  });

  it('wraps a nine-slot AMS 3H into rows of five with the incoming card above its own slot', () => {
    const nine = Array.from({ length: 9 }, (_, i) =>
      slot(i, { ams_id: 32, ams_type: 6, ...(i === 6 ? { type: '', color: '', state: 'empty' as const, incoming: incoming(0) } : {}) }),
    );
    render(<AmsPicture picture={picture([unit(nine, { ams_id: 32, ams_type: 6, kind: 'ams3h' })])} filaments={[lavaRed]} />);
    expect(screen.getByTestId('todo-ams-grid')).toHaveStyle({ gridTemplateColumns: 'repeat(5, minmax(0, 7.5rem))' });
    const slots = screen.getAllByTestId('todo-ams-slot');
    expect(slots.map((s) => [s.style.gridRow, s.style.gridColumn]).slice(4, 6)).toEqual([['3', '5'], ['6', '1']]);
    // Slot 7 is the second slot of the second row: its card is in row 4, column 2.
    expect(screen.getByTestId('todo-ams-incoming')).toHaveStyle({ gridRow: '4', gridColumn: '2' });
    expect(screen.getByTestId('todo-ams-arrow')).toHaveStyle({ gridRow: '5', gridColumn: '2' });
    expect(slots[6]).toHaveTextContent('3H-7');
  });

  it('keeps the phone layout: cards may shrink, text wraps, no fixed widths', () => {
    render(<AmsPicture picture={replaceA3} filaments={[lavaRed]} />);
    const grid = screen.getByTestId('todo-ams-grid');
    expect(grid.className).toContain('gap-x-1.5');
    for (const card of [...screen.getAllByTestId('todo-ams-slot'), screen.getByTestId('todo-ams-incoming')]) {
      expect(card.className).toContain('min-w-0');
    }
    expect(screen.getByTestId('todo-ams-picture').className).toContain('min-w-0');
  });

  it('keeps the picture as compact as the mockup on a wide screen: columns are capped, the unit hugs them', () => {
    render(<AmsPicture picture={replaceA3} filaments={[lavaRed]} />);
    expect(screen.getByTestId('todo-ams-grid')).toHaveStyle({ justifyContent: 'start' });
    expect(screen.getByTestId('todo-ams-unit').className).toContain('w-fit');
    expect(screen.getByTestId('todo-ams-unit').className).toContain('max-w-full');
  });

  it('shows no lone dash on a compact slot whose amount is not known', () => {
    const compact = picture([unit([slot(0), slot(1, { remaining_g: 90 })])], { compact: true });
    render(<AmsPicture picture={compact} filaments={[]} />);
    const cards = screen.getAllByTestId('todo-ams-slot');
    expect(cards[0].textContent).toBe('A1\u00a0');
    expect(cards[1]).toHaveTextContent('90 g');
    expect(screen.queryByText('—')).toBeNull();
  });

  it('gives each external holder of a two-nozzle printer its own unit with its nozzle', () => {
    const ext = (tray: number, nozzle: 'left' | 'right') =>
      unit([slot(tray, { ams_id: 255, is_external: true, ams_type: null })], { ams_id: 255, ams_type: null, kind: 'external', nozzle });
    render(<AmsPicture picture={picture([ext(0, 'left'), ext(1, 'right')])} filaments={[]} />);
    expect(screen.getByRole('region', { name: 'External spool · Left nozzle' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'External spool · Right nozzle' })).toBeInTheDocument();
  });

  it('has no unit written twice in a locale: the grams carry their own unit', () => {
    const locales = import.meta.glob('../../i18n/locales/*.ts', { eager: true }) as Record<string, { default: { queueTodo: { picture: Record<string, string> } } }>;
    expect(Object.keys(locales)).toHaveLength(16);
    for (const [file, mod] of Object.entries(locales)) {
      for (const key of ['newMin', 'minGrams']) {
        expect(mod.default.queueTodo.picture[key], `${file} ${key}`).toMatch(/\{\{grams\}\}(?!\s*(g|г)\b)/);
      }
    }
  });

  it('lists filaments that have no slot', () => {
    render(<AmsPicture picture={picture([unit([slot(0)])], { unplaced: [0] })} filaments={[lavaRed]} />);
    expect(screen.getByTestId('todo-ams-unplaced')).toHaveTextContent('No slot for: PLA Lava Red');
  });
});

describe('the circles of the picture are the printer card\'s slot circles', () => {
  it('draws every slot and every incoming spool with the slot circle and none with the swatch', () => {
    render(<AmsPicture picture={replaceA3} filaments={[lavaRed]} />);
    expect(screen.getAllByTestId('todo-ams-circle')).toHaveLength(4);
    expect(screen.getAllByTestId('todo-ams-incoming-circle')).toHaveLength(1);
    expect(screen.queryByTestId('filament-swatch')).toBeNull();
    // No number in a circle: the label above it names the slot.
    expect(screen.getAllByTestId('todo-ams-circle').map((c) => c.textContent)).toEqual(['', '', '', '']);
    expect(screen.getByTestId('todo-ams-incoming-circle').textContent).toBe('');
  });

  it('draws a multicolour spool in a slot as segments', () => {
    const multi = picture([
      unit([slot(0, { extra_colors: 'ec984c,6cd4bc,a66eb9', subtype: 'Multicolor', color_name: 'Rainbow' })]),
    ]);
    render(<AmsPicture picture={multi} filaments={[]} />);
    expect(screen.getByTestId('todo-ams-circle').style.backgroundImage.toLowerCase()).toMatch(/conic-gradient[^]*#ec984c/);
  });

  it('keeps the alpha of a translucent spool the backend sends as rgba', () => {
    const clear = picture([unit([slot(0, { color: '#FFFFFF', rgba: 'FFFFFF40', type: 'PETG', color_name: 'Clear' })])]);
    render(<AmsPicture picture={clear} filaments={[]} />);
    expect(screen.getByTestId('todo-ams-circle').style.backgroundImage.toLowerCase()).toContain('#ffffff40');
  });

  it('draws an empty slot as a dashed circle and dims the spool that goes out', () => {
    render(<AmsPicture picture={replaceA3} filaments={[lavaRed]} />);
    const circles = screen.getAllByTestId('todo-ams-circle');
    expect(circles[3].style.borderStyle).toBe('dashed');
    expect(circles[2].className).toContain('opacity-[0.55]');
    expect(circles[1].className).not.toContain('opacity');
  });
});

describe('the build forms', () => {
  const ext = (trayId: number, overrides: Partial<QueueTodoPictureSlot> = {}) =>
    slot(trayId, { ams_id: 255, is_external: true, ams_type: null, ...overrides });
  const extUnit = (slots: QueueTodoPictureSlot[], overrides: Partial<QueueTodoPictureUnit> = {}) =>
    unit(slots, { ams_id: 255, ams_type: null, kind: 'external', ...overrides });

  it('an AMS-HT is one slot with the new spool above it', () => {
    const ht = picture([
      unit([slot(0, { ams_id: 128, is_ht: true, ams_type: 4, state: 'out', incoming: incoming(0) })], { ams_id: 128, ams_type: 4, kind: 'ht' }),
    ]);
    render(<AmsPicture picture={ht} filaments={[lavaRed]} />);
    expect(screen.getAllByTestId('todo-ams-slot')).toHaveLength(1);
    expect(screen.getByTestId('todo-ams-incoming')).toHaveStyle({ gridRow: '1', gridColumn: '1' });
    expect(screen.getByTestId('todo-ams-slot')).toHaveTextContent('HT-A');
  });

  it('the external spool alone is the only slot, with Ext and the new spool above it', () => {
    const only = picture([extUnit([ext(0, { type: '', color: '', state: 'empty', incoming: incoming(0) })])]);
    render(<AmsPicture picture={only} filaments={[lavaRed]} />);
    expect(screen.getAllByTestId('todo-ams-unit')).toHaveLength(1);
    expect(screen.getByTestId('todo-ams-unit')).toHaveAccessibleName('External spool');
    expect(screen.getByTestId('todo-ams-slot')).toHaveTextContent('Ext');
    expect(screen.getByTestId('todo-ams-incoming')).toBeInTheDocument();
    expect(screen.getByTestId('todo-ams-circle').style.borderStyle).toBe('dashed');
  });

  it('a printer without an AMS whose external spool is the wrong filament puts the new spool above it', () => {
    const wrong = picture([extUnit([ext(0, { type: 'PETG', color: '#00FF00', state: 'out', incoming: incoming(0) })])]);
    render(<AmsPicture picture={wrong} filaments={[lavaRed]} />);
    expect(screen.getByTestId('todo-ams-slot')).toHaveAttribute('data-state', 'out');
    expect(screen.getByTestId('todo-ams-incoming')).toHaveTextContent('Lava Red');
    expect(screen.getByTestId('todo-ams-arrow')).toHaveStyle({ gridColumn: '1' });
  });

  it('an H2D folds the external holders nothing goes into behind the toggle, as it does an AMS', () => {
    const h2d = picture([
      unit([slot(0), slot(1), slot(2), slot(3, { type: '', color: '', state: 'empty', incoming: incoming(0) })], { ams_id: 0, nozzle: 'right' }),
      unit([slot(0, { ams_id: 1 }), slot(1, { ams_id: 1 }), slot(2, { ams_id: 1 }), slot(3, { ams_id: 1 })], { ams_id: 1, nozzle: 'left' }),
      extUnit([ext(0)], { nozzle: 'left', collapsed: true }),
      extUnit([ext(1)], { nozzle: 'right', collapsed: true }),
    ]);
    render(<AmsPicture picture={h2d} filaments={[lavaRed]} />);
    expect(screen.getAllByTestId('todo-ams-unit').map((u) => u.getAttribute('aria-label'))).toEqual([
      'AMS-A · Right nozzle',
      'AMS-B · Left nozzle',
    ]);
    const toggle = screen.getByRole('button', { name: /External spool · Left nozzle, External spool · Right nozzle/ });
    fireEvent.click(toggle);
    expect(screen.getAllByTestId('todo-ams-unit')).toHaveLength(4);
  });

  it('an AMS 3H draws nine circles', () => {
    const nine = Array.from({ length: 9 }, (_, i) => slot(i, { ams_id: 32, ams_type: 6 }));
    render(<AmsPicture picture={picture([unit(nine, { ams_id: 32, ams_type: 6, kind: 'ams3h' })])} filaments={[]} />);
    expect(screen.getAllByTestId('todo-ams-circle').map((c) => c.textContent)).toEqual(Array(9).fill(''));
  });
});

describe('AmsPictures', () => {
  const second = { ...picture([unit([slot(0, { type: '', color: '', state: 'empty', incoming: incoming(0) })])]), printer_id: 2, printer_name: 'Shelf X1C' };

  it('shows the printer likely to take the job first and switches to the others', () => {
    render(<AmsPictures pictures={[replaceA3, second]} filaments={[lavaRed]} />);
    const first = screen.getByRole('button', { name: /Shelf P1S right/ });
    expect(first).toHaveAttribute('aria-pressed', 'true');
    expect(first).toHaveTextContent('likely next');
    expect(screen.getAllByTestId('todo-ams-slot')).toHaveLength(4);
    fireEvent.click(screen.getByRole('button', { name: 'Shelf X1C' }));
    expect(screen.getByRole('button', { name: 'Shelf X1C' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByTestId('todo-ams-slot')).toHaveLength(1);
  });

  it('draws exactly one picture, however often the list refetches and the printer is switched', () => {
    const folded = picture([unit([slot(0)], { collapsed: true }), unit([slot(0, { type: '', color: '', state: 'empty', incoming: incoming(0) })], { ams_id: 1 })]);
    const mk = () => <AmsPictures pictures={[folded, { ...second, units: folded.units }]} filaments={[lavaRed]} />;
    const { rerender } = render(mk());
    rerender(mk());
    fireEvent.click(screen.getByRole('button', { name: 'Show AMS-A' }));
    expect(screen.getAllByTestId('todo-ams-unit')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Shelf X1C' }));
    rerender(mk());
    expect(screen.getAllByTestId('todo-ams-picture')).toHaveLength(1);
    // The other printer starts folded again.
    expect(screen.getAllByTestId('todo-ams-unit')).toHaveLength(1);
  });

  it('has no switch for a single printer and renders nothing for none', () => {
    const { container, rerender } = render(<AmsPictures pictures={[replaceA3]} filaments={[lavaRed]} />);
    expect(screen.queryByRole('group')).toBeNull();
    rerender(<AmsPictures pictures={[]} filaments={[]} />);
    expect(container.querySelector('[data-testid="todo-ams-picture"]')).toBeNull();
  });
});

describe('the picture in the To do list', () => {
  const entry = (extra: object) => ({
    kind: 'load_filament' as const,
    jobs: [{ id: 11, name: 'Lamp_Base.5x.P1S.3mf', can_start: true }],
    filaments: [lavaRed],
    printers: [],
    detail: null,
    ...extra,
  });
  const listOf = (e: object, prepare: object[] = []): QueueTodo => ({
    count: 1,
    groups: [{ printer_id: 1, printer_name: 'Shelf P1S right', target_model: null, entries: [entry(e)], prepare: prepare as never }],
  });

  it('draws the picture instead of the slot sentence and names a short spool entry', () => {
    const slotHint = { state: 'replace' as const, slots: [], unknown_jobs: 0, by_nozzle: [] };
    render(<QueueTodoList todo={listOf({ ams_picture: replaceA3, slot_hint: slotHint })} />);
    expect(screen.getByTestId('todo-ams-picture')).toBeInTheDocument();
    expect(screen.queryByTestId('todo-slot-hint')).toBeNull();
    expect(screen.getByTestId('todo-entry-load_filament')).toHaveTextContent('Replace spool');
    // The sentence about the amounts stays: text for those who do not read the picture.
    expect(screen.getByTestId('todo-short')).toBeInTheDocument();
  });

  it('keeps the sentence when the entry has no picture', () => {
    const slotHint = { state: 'free' as const, slots: [{ ams_id: 0, tray_id: 3, is_ht: false, is_external: false, ams_type: 1, nozzle: null, type: '', color: '', tray_info_idx: '', tray_sub_brands: '' }], unknown_jobs: 0, by_nozzle: [] };
    render(<QueueTodoList todo={listOf({ slot_hint: slotHint, ams_picture: null })} />);
    expect(screen.queryByTestId('todo-ams-picture')).toBeNull();
    expect(screen.getByTestId('todo-slot-hint')).toHaveTextContent('Free: A4');
  });

  it('titles an entry of several filaments with their count', () => {
    const fils = [{ ...lavaRed, short: false }, { ...lavaRed, short: false, color_name: 'Jadeite' }];
    render(<QueueTodoList todo={listOf({ filaments: fils, ams_picture: replaceA3 })} />);
    expect(screen.getByTestId('todo-entry-load_filament')).toHaveTextContent('Load 2 filaments');
  });

  it('shows a compact picture under a prepare line instead of its sentence', () => {
    const line = {
      job: { id: 12, name: 'Lamp_Shade.3mf' },
      position: 1,
      filaments: [{ type: 'PETG', color: '#FF69B4', color_name: 'Pink', no_stock: false }],
      slot_hint: { state: 'free', slots: [], unknown_jobs: 0, by_nozzle: [] },
      ams_picture: picture([unit([slot(0), slot(1, { type: '', color: '', state: 'empty', incoming: incoming(0) })])], { compact: true }),
    };
    const todo: QueueTodo = { count: 0, groups: [{ printer_id: 1, printer_name: 'Shelf P1S right', target_model: null, entries: [], prepare: [line as never] }] };
    render(<QueueTodoList todo={todo} />);
    expect(screen.getByTestId('todo-ams-picture')).toHaveAttribute('data-compact', 'true');
    expect(screen.queryByTestId('todo-prepare-hint')).toBeNull();
    expect(screen.getByTestId('todo-prepare-row')).toHaveTextContent('Lamp_Shade.3mf');
  });

  it('draws the printer a model job would likely go to first, with the others one tap away', () => {
    const model: QueueTodo = {
      count: 1,
      groups: [{
        printer_id: null, printer_name: 'P1S', target_model: 'P1S',
        entries: [{ ...entry({}), printers: [{ id: 1, name: 'Shelf P1S right' }, { id: 2, name: 'Shelf X1C' }], ams_pictures: [replaceA3, { ...replaceA3, printer_id: 2, printer_name: 'Shelf X1C' }] }],
        prepare: [],
      }],
    };
    render(<QueueTodoList todo={model} />);
    expect(screen.getByTestId('todo-ams-picture')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Shelf X1C/ })).toHaveLength(1);
  });
});
