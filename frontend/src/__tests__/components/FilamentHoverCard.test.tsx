/**
 * Tests for the FilamentHoverCard component.
 * Focuses on fill level display and Spoolman source indicator.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, createEvent, waitFor, act } from '../utils';
import { FilamentHoverCard, EmptySlotHoverCard } from '../../components/FilamentHoverCard';
import { setColorCatalog, __resetColorCatalogForTests } from '../../utils/colors';

const baseFilamentData = {
  vendor: 'Bambu Lab' as const,
  profile: 'PLA Basic',
  colorName: 'Red',
  colorHex: 'FF0000',
  kFactor: '0.030',
  fillLevel: 75,
  trayUuid: 'A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4',
};

function renderWithHover(ui: React.ReactElement) {
  const result = render(ui);
  // Trigger hover to show the card
  const trigger = result.container.firstElementChild as HTMLElement;
  fireEvent.mouseEnter(trigger);
  return result;
}

describe('FilamentHoverCard', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  describe('fill level display', () => {
    it('shows fill percentage when fillLevel is set', async () => {
      renderWithHover(
        <FilamentHoverCard data={{ ...baseFilamentData, fillLevel: 75 }}>
          <div>trigger</div>
        </FilamentHoverCard>
      );

      vi.advanceTimersByTime(100);

      await waitFor(() => {
        expect(screen.getByText('75%')).toBeInTheDocument();
      });
    });

    it('shows dash when fillLevel is null', async () => {
      renderWithHover(
        <FilamentHoverCard data={{ ...baseFilamentData, fillLevel: null }}>
          <div>trigger</div>
        </FilamentHoverCard>
      );

      vi.advanceTimersByTime(100);

      await waitFor(() => {
        expect(screen.getByText('—')).toBeInTheDocument();
      });
    });

    it('shows 0% when fillLevel is zero', async () => {
      renderWithHover(
        <FilamentHoverCard data={{ ...baseFilamentData, fillLevel: 0 }}>
          <div>trigger</div>
        </FilamentHoverCard>
      );

      vi.advanceTimersByTime(100);

      await waitFor(() => {
        expect(screen.getByText('0%')).toBeInTheDocument();
      });
    });
  });

  describe('fill source badge transparency (#11)', () => {
    it('never shows a Spoolman-source badge — UI stays mode-agnostic', async () => {
      renderWithHover(
        <FilamentHoverCard data={{ ...baseFilamentData, fillLevel: 80, fillSource: 'spoolman' }}>
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => {
        expect(screen.getByText('80%')).toBeInTheDocument();
        expect(screen.queryByText('(Spoolman)')).not.toBeInTheDocument();
      });
    });

    it('never shows an inventory-source badge — UI stays mode-agnostic', async () => {
      renderWithHover(
        <FilamentHoverCard data={{ ...baseFilamentData, fillLevel: 80, fillSource: 'inventory' }}>
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => {
        expect(screen.getByText('80%')).toBeInTheDocument();
        expect(screen.queryByText('(Inv)')).not.toBeInTheDocument();
      });
    });

    it('does not render an empty source-label span when fillLevel is null', async () => {
      renderWithHover(
        <FilamentHoverCard data={{ ...baseFilamentData, fillLevel: null, fillSource: 'spoolman' }}>
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => {
        expect(screen.getByText('—')).toBeInTheDocument();
        expect(screen.queryByText('(Spoolman)')).not.toBeInTheDocument();
        expect(screen.queryByText('(Inv)')).not.toBeInTheDocument();
      });
    });
  });

  describe('hover behavior', () => {
    it('does not show card when disabled', () => {
      renderWithHover(
        <FilamentHoverCard data={baseFilamentData} disabled>
          <div>trigger</div>
        </FilamentHoverCard>
      );

      vi.advanceTimersByTime(100);

      // Card should not be visible
      expect(screen.queryByText('PLA Basic')).not.toBeInTheDocument();
    });

    it('shows filament details on hover', async () => {
      renderWithHover(
        <FilamentHoverCard data={baseFilamentData}>
          <div>trigger</div>
        </FilamentHoverCard>
      );

      vi.advanceTimersByTime(100);

      await waitFor(() => {
        expect(screen.getByText('Red')).toBeInTheDocument();
        expect(screen.getByText('PLA Basic')).toBeInTheDocument();
        expect(screen.getByText('0.030')).toBeInTheDocument();
      });
    });
  });

  // The inventory section was previously hidden for `vendor === 'Bambu Lab'`
  // because BL spools were assumed to be managed entirely via RFID. #1133
  // removed that gate so users who don't want to scan via SpoolBuddy NFC
  // can still pick a BL spool from inventory the same way they pick a
  // third-party one.
  // Paired with the EmptySlotHoverCard assertion below (#2791) — together
  // they pin the two render paths to the same Assign-then-Configure order.
  it('lists Assign Spool above Configure (#2791)', async () => {
    renderWithHover(
      <FilamentHoverCard
        data={baseFilamentData}
        inventory={{ assignedSpool: null, onAssignSpool: vi.fn() }}
        configureSlot={{ enabled: true, onConfigure: vi.fn() }}
      >
        <div>trigger</div>
      </FilamentHoverCard>
    );
    vi.advanceTimersByTime(100);
    await waitFor(() => expect(screen.getByText(/assign spool/i)).toBeInTheDocument());

    const assign = screen.getByText(/assign spool/i);
    const configure = screen.getByText(/^configure$/i);
    expect(assign.compareDocumentPosition(configure)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    );
  });

  describe('inventory section vendor visibility (#1133)', () => {
    it('shows the assign-spool button on a Bambu Lab slot when the spool is unassigned', async () => {
      const onAssign = vi.fn();
      renderWithHover(
        <FilamentHoverCard
          data={{ ...baseFilamentData, vendor: 'Bambu Lab' }}
          inventory={{ assignedSpool: null, onAssignSpool: onAssign }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => {
        expect(screen.getByText(/assign/i)).toBeInTheDocument();
      });
    });

    it('shows the unassign button on a Bambu Lab slot when an inventory spool is already assigned', async () => {
      // Regression guard: the original gate hid BOTH the assign and unassign
      // buttons for BL slots. A user who'd already assigned an inventory
      // spool to a BL slot couldn't undo it without dropping into the
      // inventory page directly.
      const onUnassign = vi.fn();
      renderWithHover(
        <FilamentHoverCard
          data={{ ...baseFilamentData, vendor: 'Bambu Lab' }}
          inventory={{
            assignedSpool: {
              id: 1,
              material: 'PLA',
              subtype: null,
              brand: 'Devil Design',
              color_name: 'Black',
            },
            onUnassignSpool: onUnassign,
          }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => {
        expect(screen.getByText(/unassign/i)).toBeInTheDocument();
      });
    });

    it('still shows the assign-spool button for a non-Bambu vendor (no behaviour change)', async () => {
      const onAssign = vi.fn();
      renderWithHover(
        <FilamentHoverCard
          data={{ ...baseFilamentData, vendor: 'Polymaker' as unknown as 'Bambu Lab' }}
          inventory={{ assignedSpool: null, onAssignSpool: onAssign }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => {
        expect(screen.getByText(/assign/i)).toBeInTheDocument();
      });
    });

    it('shows the assign-spool button as disabled when isAssigned=true', async () => {
      const onAssign = vi.fn();
      renderWithHover(
        <FilamentHoverCard
          data={{ ...baseFilamentData, vendor: 'Bambu Lab' }}
          inventory={{ assignedSpool: null, onAssignSpool: onAssign, isAssigned: true }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => {
        expect(screen.getByText(/assign/i)).toBeInTheDocument();
        expect(screen.getByText(/assign/i).closest('button')).toBeDisabled();
      });
    });

    it('does not call onAssignSpool when the button is disabled via isAssigned', async () => {
      const onAssign = vi.fn();
      renderWithHover(
        <FilamentHoverCard
          data={{ ...baseFilamentData, vendor: 'Bambu Lab' }}
          inventory={{ assignedSpool: null, onAssignSpool: onAssign, isAssigned: true }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => expect(screen.getByText(/assign/i)).toBeInTheDocument());
      const btn = screen.getByText(/assign/i).closest('button')!;
      btn.click();
      expect(onAssign).not.toHaveBeenCalled();
    });
  });

  // For RFID-synced BL spools, both spoolman.linkedSpoolId and
  // inventory.assignedSpool.id point to the same Spoolman spool. Rendering
  // both branches gave two identical "Open in Inventory" buttons. The
  // inventory-side button is suppressed when it would duplicate the
  // spoolman-side link.
  describe('"Open in Inventory" deduplication', () => {
    const inventorySpool = {
      id: 42,
      material: 'PLA',
      subtype: null,
      brand: 'eSun',
      color_name: 'Black',
    };

    it('shows only one Open in Inventory button when spoolman linkedSpoolId matches assignedSpool id', async () => {
      renderWithHover(
        <FilamentHoverCard
          data={baseFilamentData}
          spoolman={{ enabled: true, linkedSpoolId: 42 }}
          inventory={{ assignedSpool: inventorySpool }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => {
        expect(screen.getByText(/assigned/i)).toBeInTheDocument();
      });
      expect(screen.queryAllByTitle('Open in Inventory')).toHaveLength(1);
    });

    it('shows two Open in Inventory buttons when spoolman and inventory point to different spools', async () => {
      renderWithHover(
        <FilamentHoverCard
          data={baseFilamentData}
          spoolman={{ enabled: true, linkedSpoolId: 99 }}
          inventory={{ assignedSpool: inventorySpool }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => {
        expect(screen.getByText(/assigned/i)).toBeInTheDocument();
      });
      expect(screen.queryAllByTitle('Open in Inventory')).toHaveLength(2);
    });

    it('shows one Open in Inventory button when spoolman is absent but inventory spool is assigned', async () => {
      renderWithHover(
        <FilamentHoverCard
          data={baseFilamentData}
          inventory={{ assignedSpool: inventorySpool }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => {
        expect(screen.getByText(/assigned/i)).toBeInTheDocument();
      });
      expect(screen.queryAllByTitle('Open in Inventory')).toHaveLength(1);
    });

    it('shows the spool ID in the assigned-spool block', async () => {
      renderWithHover(
        <FilamentHoverCard
          data={baseFilamentData}
          inventory={{ assignedSpool: inventorySpool }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => {
        expect(screen.getByText('#42')).toBeInTheDocument();
      });
    });
  });

  // The card is portaled at z-[60] — above ConfigureAmsSlotModal and
  // LinkSpoolModal at z-50 — so a card left standing draws OVER the dialog its
  // own button just opened. Mouseleave is the only thing that used to hide it,
  // and a touch device never sends one after the tap that opened the card, so on
  // a tablet it hung there indefinitely: two overlapping layers, competing focus.
  describe('dismissal when an action opens a dialog (#2631)', () => {
    it('closes the card when Configure is pressed, and still configures', async () => {
      const onConfigure = vi.fn();
      renderWithHover(
        <FilamentHoverCard
          data={baseFilamentData}
          configureSlot={{ enabled: true, onConfigure }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => expect(screen.getByText(/configure/i)).toBeInTheDocument());

      fireEvent.click(screen.getByText(/configure/i));

      expect(onConfigure).toHaveBeenCalledTimes(1);
      await waitFor(() => expect(screen.queryByText('PLA Basic')).not.toBeInTheDocument());
    });

    it('stays closed with no mouseleave, which is all a tablet ever gives us', async () => {
      renderWithHover(
        <FilamentHoverCard
          data={baseFilamentData}
          configureSlot={{ enabled: true, onConfigure: vi.fn() }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => expect(screen.getByText(/configure/i)).toBeInTheDocument());

      fireEvent.click(screen.getByText(/configure/i));
      await waitFor(() => expect(screen.queryByText('PLA Basic')).not.toBeInTheDocument());

      // A pending show timer would resurrect the card on top of the dialog.
      vi.advanceTimersByTime(1000);
      expect(screen.queryByText('PLA Basic')).not.toBeInTheDocument();
    });

    it('closes the card when Assign Spool is pressed', async () => {
      const onAssignSpool = vi.fn();
      renderWithHover(
        <FilamentHoverCard
          data={baseFilamentData}
          inventory={{ assignedSpool: null, onAssignSpool }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => expect(screen.getByText(/assign/i)).toBeInTheDocument());

      fireEvent.click(screen.getByText(/assign/i));

      expect(onAssignSpool).toHaveBeenCalledTimes(1);
      await waitFor(() => expect(screen.queryByText('PLA Basic')).not.toBeInTheDocument());
    });

    it('closes the card when Unassign Spool is pressed', async () => {
      const onUnassignSpool = vi.fn();
      renderWithHover(
        <FilamentHoverCard
          data={baseFilamentData}
          inventory={{
            assignedSpool: { id: 7, material: 'PLA', subtype: null, brand: 'eSun', color_name: 'Black' },
            onUnassignSpool,
          }}
        >
          <div>trigger</div>
        </FilamentHoverCard>
      );
      vi.advanceTimersByTime(100);
      await waitFor(() => expect(screen.getByText(/unassign/i)).toBeInTheDocument());

      fireEvent.click(screen.getByText(/unassign/i));

      expect(onUnassignSpool).toHaveBeenCalledTimes(1);
      await waitFor(() => expect(screen.queryByText('PLA Basic')).not.toBeInTheDocument());
    });
  });
});

// EmptySlotHoverCard is the hover wrapper rendered for a physically empty
// AMS slot. #1133 removed its inventory affordance: a slot with nothing
// loaded has no spool to attach an inventory record to, and offering the
// action there only led to users assigning the wrong spool to a slot the
// printer hadn't actually loaded yet. The configure-slot affordance is
// kept, since "preset for the next spool to land here" is still a sensible
// thing to do on an empty slot.
describe('EmptySlotHoverCard (#1133)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it('does not render an assign-spool button when onAssignSpool is not provided', async () => {
    const result = render(
      <EmptySlotHoverCard configureSlot={{ enabled: true, onConfigure: vi.fn() }}>
        <div>trigger</div>
      </EmptySlotHoverCard>
    );
    fireEvent.mouseEnter(result.container.firstElementChild as HTMLElement);
    vi.advanceTimersByTime(100);
    await waitFor(() => {
      // The card itself is showing — guard the negative assertion against
      // a card that simply never opened.
      expect(screen.getByText(/empty/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/assign spool/i)).not.toBeInTheDocument();
  });

  it('still shows the configure button on an empty slot', async () => {
    const onConfigure = vi.fn();
    const result = render(
      <EmptySlotHoverCard configureSlot={{ enabled: true, onConfigure }}>
        <div>trigger</div>
      </EmptySlotHoverCard>
    );
    fireEvent.mouseEnter(result.container.firstElementChild as HTMLElement);
    vi.advanceTimersByTime(100);
    await waitFor(() => {
      expect(screen.getByText(/configure/i)).toBeInTheDocument();
    });
  });

  it('shows Assign Spool button when onAssignSpool is provided', async () => {
    const onAssign = vi.fn();
    const result = render(
      <EmptySlotHoverCard onAssignSpool={onAssign}>
        <div>trigger</div>
      </EmptySlotHoverCard>
    );
    fireEvent.mouseEnter(result.container.firstElementChild as HTMLElement);
    vi.advanceTimersByTime(100);
    await waitFor(() => {
      expect(screen.getByText(/assign spool/i)).toBeInTheDocument();
    });
  });

  it('calls onAssignSpool when Assign Spool button is clicked', async () => {
    const onAssign = vi.fn();
    const result = render(
      <EmptySlotHoverCard onAssignSpool={onAssign}>
        <div>trigger</div>
      </EmptySlotHoverCard>
    );
    fireEvent.mouseEnter(result.container.firstElementChild as HTMLElement);
    vi.advanceTimersByTime(100);
    await waitFor(() => expect(screen.getByText(/assign spool/i)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/assign spool/i));
    expect(onAssign).toHaveBeenCalledTimes(1);
  });

  // #2791: the empty-slot and filled-slot cards are separate render paths
  // that had drifted into opposite orders, so the menu reshuffled itself
  // depending on whether the slot happened to hold filament. Both now put
  // the spool action above the slot action; assert it on both paths so the
  // two can't drift apart again.
  it('lists Assign Spool above Configure, matching the filled-slot card (#2791)', async () => {
    const result = render(
      <EmptySlotHoverCard
        configureSlot={{ enabled: true, onConfigure: vi.fn() }}
        onAssignSpool={vi.fn()}
      >
        <div>trigger</div>
      </EmptySlotHoverCard>
    );
    fireEvent.mouseEnter(result.container.firstElementChild as HTMLElement);
    vi.advanceTimersByTime(100);
    await waitFor(() => expect(screen.getByText(/assign spool/i)).toBeInTheDocument());

    const assign = screen.getByText(/assign spool/i);
    const configure = screen.getByText(/^configure$/i);
    expect(assign.compareDocumentPosition(configure)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    );
  });

  // Same z-[60]-over-a-z-50-dialog problem as FilamentHoverCard (#2631).
  describe('dismissal when an action opens a dialog (#2631)', () => {
    it('closes the card when Configure is pressed, and still configures', async () => {
      const onConfigure = vi.fn();
      const result = render(
        <EmptySlotHoverCard configureSlot={{ enabled: true, onConfigure }}>
          <div>trigger</div>
        </EmptySlotHoverCard>
      );
      fireEvent.mouseEnter(result.container.firstElementChild as HTMLElement);
      vi.advanceTimersByTime(100);
      await waitFor(() => expect(screen.getByText(/configure/i)).toBeInTheDocument());

      fireEvent.click(screen.getByText(/configure/i));

      expect(onConfigure).toHaveBeenCalledTimes(1);
      await waitFor(() => expect(screen.queryByText(/empty/i)).not.toBeInTheDocument());
    });

    it('closes the card when Assign Spool is pressed', async () => {
      const onAssign = vi.fn();
      const result = render(
        <EmptySlotHoverCard onAssignSpool={onAssign}>
          <div>trigger</div>
        </EmptySlotHoverCard>
      );
      fireEvent.mouseEnter(result.container.firstElementChild as HTMLElement);
      vi.advanceTimersByTime(100);
      await waitFor(() => expect(screen.getByText(/assign spool/i)).toBeInTheDocument());

      fireEvent.click(screen.getByText(/assign spool/i));

      expect(onAssign).toHaveBeenCalledTimes(1);
      await waitFor(() => expect(screen.queryByText(/empty/i)).not.toBeInTheDocument());
    });
  });
});

describe('FilamentHoverCard colour name (#2875)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    __resetColorCatalogForTests();
  });

  const whiteMatte = {
    ...baseFilamentData,
    profile: 'Bambu PLA Matte',
    colorHex: 'FFFFFFFF',
    // What PrintersPage now resolves with the slot's own tray_sub_brands.
    colorName: 'Ivory White',
  };

  async function showCard(ui: React.ReactElement) {
    renderWithHover(ui);
    vi.advanceTimersByTime(100);
  }

  it('shows the resolved catalogue name for the slot', async () => {
    await showCard(
      <FilamentHoverCard data={whiteMatte}>
        <div>trigger</div>
      </FilamentHoverCard>
    );

    await waitFor(() => expect(screen.getByText('Ivory White')).toBeInTheDocument());
    expect(screen.queryByText('Jade White')).not.toBeInTheDocument();
  });

  it('prefers the assigned spool name, which is what the user put in the slot', async () => {
    await showCard(
      <FilamentHoverCard
        data={{ ...whiteMatte, colorName: 'Jade White' }}
        inventory={{
          isAssigned: true,
          assignedSpool: { id: 17, material: 'PLA', subtype: null, brand: 'Bambu Lab', color_name: 'Matte Ivory White' },
        }}
      >
        <div>trigger</div>
      </FilamentHoverCard>
    );

    await waitFor(() => expect(screen.getByText('Matte Ivory White')).toBeInTheDocument());
    expect(screen.queryByText('Jade White')).not.toBeInTheDocument();
  });

  it('ignores a Bambu internal colour code on the assigned spool', async () => {
    // "A06-D0" is not a name, and is not unique across material families
    // (#857) -- the catalogue answer stands.
    await showCard(
      <FilamentHoverCard
        data={whiteMatte}
        inventory={{
          isAssigned: true,
          assignedSpool: { id: 17, material: 'PLA', subtype: null, brand: 'Bambu Lab', color_name: 'A06-D0' },
        }}
      >
        <div>trigger</div>
      </FilamentHoverCard>
    );

    await waitFor(() => expect(screen.getByText('Ivory White')).toBeInTheDocument());
    expect(screen.queryByText('A06-D0')).not.toBeInTheDocument();
  });

  it.each([
    ['an empty colour name', ''],
    ['a whitespace-only colour name', '   '],
  ])('keeps the catalogue answer for a spool with %s', async (_label, colorName) => {
    await showCard(
      <FilamentHoverCard
        data={whiteMatte}
        inventory={{
          isAssigned: true,
          assignedSpool: { id: 17, material: 'PLA', subtype: null, brand: 'Bambu Lab', color_name: colorName },
        }}
      >
        <div>trigger</div>
      </FilamentHoverCard>
    );

    await waitFor(() => expect(screen.getByText('Ivory White')).toBeInTheDocument());
  });

  it('keeps the catalogue answer when a spool is assigned with no colour recorded', async () => {
    setColorCatalog({ ffffff: 'Jade White' }, { 'pla matte|ffffff': 'Ivory White' });

    await showCard(
      <FilamentHoverCard
        data={whiteMatte}
        inventory={{
          isAssigned: true,
          assignedSpool: { id: 17, material: 'PLA', subtype: null, brand: 'Bambu Lab', color_name: null },
        }}
      >
        <div>trigger</div>
      </FilamentHoverCard>
    );

    await waitFor(() => expect(screen.getByText('Ivory White')).toBeInTheDocument());
  });
});

// A spool's subtype is part of its name. Dropping it made a wood-filled roll
// read as plain PLA on the slot card, which is the display-side version of
// the mistake #2902 fixed on the backend -- and the printer, the inventory
// page and Studio all named it correctly at the same time, so the card was
// the only thing saying otherwise.
describe('FilamentHoverCard assigned spool name', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    __resetColorCatalogForTests();
  });

  function showAssigned(assignedSpool: {
    id: number;
    material: string;
    subtype: string | null;
    brand: string | null;
    color_name: string | null;
  }) {
    renderWithHover(
      <FilamentHoverCard data={baseFilamentData} inventory={{ isAssigned: true, assignedSpool }}>
        <div>trigger</div>
      </FilamentHoverCard>
    );
    vi.advanceTimersByTime(100);
  }

  it('names a filled filament by its subtype, not by its base material', async () => {
    showAssigned({
      id: 77,
      material: 'PLA',
      subtype: 'Wood',
      brand: 'Bambu Lab',
      color_name: 'Classic Birch',
    });

    await waitFor(() =>
      expect(screen.getByText('Bambu Lab PLA Wood - Classic Birch')).toBeInTheDocument()
    );
  });

  it('omits the subtype entirely for a spool that has none', async () => {
    showAssigned({
      id: 78,
      material: 'PLA',
      subtype: null,
      brand: 'Bambu Lab',
      color_name: 'Jade White',
    });

    await waitFor(() =>
      expect(screen.getByText('Bambu Lab PLA - Jade White')).toBeInTheDocument()
    );
  });
});

/**
 * The header swatch (#2967).
 *
 * A tray record carries one `tray_color` hex and nothing else, so telemetry can
 * never describe a gradient or a surface effect. The reporter's Ziro "Colorful
 * Mist" -- yellow, cyan and pink, effect Tri Color -- painted the header as one
 * flat band of the single hex the slot happened to be configured with. The
 * spool knows better, and the header now paints the spool's own swatch through
 * the same builder the Inventory swatches use.
 */
describe('FilamentHoverCard — assigned spool swatch (#2967)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  const triColorSpool = {
    id: 191,
    material: 'PLA',
    subtype: 'Matte',
    brand: 'Ziro',
    color_name: 'Colorful Mist',
    rgba: 'FFB6C1FF',
    extra_colors: 'ffff00,00ffff,ffb6c1',
    effect_type: 'tri-color',
  };

  // The swatch header is the card's first child: a fixed-height block carrying
  // the colour and the name. Queried off `document` rather than the render
  // container because the card is portaled into document.body.
  function header(): HTMLElement {
    const el = document.querySelector('.h-12') as HTMLElement | null;
    expect(el, 'header block not found').not.toBeNull();
    return el as HTMLElement;
  }

  it('paints the gradient for a multi-colour spool', async () => {
    renderWithHover(
      <FilamentHoverCard data={baseFilamentData} inventory={{ assignedSpool: triColorSpool }}>
        <div>trigger</div>
      </FilamentHoverCard>
    );
    vi.advanceTimersByTime(100);
    await waitFor(() => expect(screen.getByText('Colorful Mist')).toBeInTheDocument());
    expect(header().style.backgroundImage).toContain('gradient');
  });

  it('carries every stop the spool declared', async () => {
    renderWithHover(
      <FilamentHoverCard data={baseFilamentData} inventory={{ assignedSpool: triColorSpool }}>
        <div>trigger</div>
      </FilamentHoverCard>
    );
    vi.advanceTimersByTime(100);
    await waitFor(() => expect(screen.getByText('Colorful Mist')).toBeInTheDocument());
    const image = header().style.backgroundImage.toLowerCase();
    expect(image).toContain('#ffff00');
    expect(image).toContain('#00ffff');
    expect(image).toContain('#ffb6c1');
  });

  it('leaves a plain single-colour spool on the flat slot colour', async () => {
    // The common case must not go anywhere near the gradient machinery.
    renderWithHover(
      <FilamentHoverCard
        data={baseFilamentData}
        inventory={{
          assignedSpool: { ...triColorSpool, extra_colors: null, effect_type: null },
        }}
      >
        <div>trigger</div>
      </FilamentHoverCard>
    );
    vi.advanceTimersByTime(100);
    await waitFor(() => expect(screen.getByText('Colorful Mist')).toBeInTheDocument());
    expect(header().style.backgroundImage).toBe('');
  });

  it('paints the swatch for an effect with no extra colours', async () => {
    // A silk roll is one colour with a surface the hex cannot express.
    renderWithHover(
      <FilamentHoverCard
        data={baseFilamentData}
        inventory={{ assignedSpool: { ...triColorSpool, extra_colors: null, effect_type: 'silk' } }}
      >
        <div>trigger</div>
      </FilamentHoverCard>
    );
    vi.advanceTimersByTime(100);
    await waitFor(() => expect(screen.getByText('Colorful Mist')).toBeInTheDocument());
    expect(header().style.backgroundImage).not.toBe('');
  });

  it('puts the name on a scrim when the background has several bands', async () => {
    // One hex cannot decide legibility across yellow, cyan and pink, and the
    // label sits dead centre where the background is most likely to change.
    renderWithHover(
      <FilamentHoverCard data={baseFilamentData} inventory={{ assignedSpool: triColorSpool }}>
        <div>trigger</div>
      </FilamentHoverCard>
    );
    vi.advanceTimersByTime(100);
    await waitFor(() => expect(screen.getByText('Colorful Mist')).toBeInTheDocument());
    expect(screen.getByText('Colorful Mist').className).toContain('bg-black/60');
  });

  it('does not scrim a single-colour spool', async () => {
    renderWithHover(
      <FilamentHoverCard
        data={baseFilamentData}
        inventory={{
          assignedSpool: { ...triColorSpool, extra_colors: null, effect_type: null },
        }}
      >
        <div>trigger</div>
      </FilamentHoverCard>
    );
    vi.advanceTimersByTime(100);
    await waitFor(() => expect(screen.getByText('Colorful Mist')).toBeInTheDocument());
    expect(screen.getByText('Colorful Mist').className).not.toContain('bg-black/60');
  });

  it('keeps a slot with no assigned spool exactly as it was', async () => {
    renderWithHover(
      <FilamentHoverCard data={baseFilamentData} inventory={{ assignedSpool: null }}>
        <div>trigger</div>
      </FilamentHoverCard>
    );
    vi.advanceTimersByTime(100);
    await waitFor(() => expect(screen.getByText('Red')).toBeInTheDocument());
    expect(header().style.backgroundImage).toBe('');
  });

  it('tolerates a spool that predates the swatch fields', async () => {
    // Older callers send neither rgba nor extra_colors; the optional fields
    // must not turn that into a blank or a crash.
    renderWithHover(
      <FilamentHoverCard
        data={baseFilamentData}
        inventory={{
          assignedSpool: { id: 1, material: 'PLA', subtype: null, brand: 'Ziro', color_name: 'Mist' },
        }}
      >
        <div>trigger</div>
      </FilamentHoverCard>
    );
    vi.advanceTimersByTime(100);
    await waitFor(() => expect(screen.getByText('Mist')).toBeInTheDocument());
    expect(header().style.backgroundImage).toBe('');
  });
});

// The tile is the tap target (#3577): a tap on the material text selected the
// word on a phone and the card, which only listened for mouseenter, never opened.
// jsdom's pointer events carry no pointerType, so stamp one on like a browser would.
const pointer = (el: Element, type: 'pointerDown' | 'pointerEnter', pointerType: string) => {
  const ev = createEvent[type](el);
  Object.defineProperty(ev, 'pointerType', { value: pointerType });
  fireEvent(el, ev);
};

const advance = (ms: number) => act(() => { vi.advanceTimersByTime(ms); });

describe.each([
  ['FilamentHoverCard', 'filament-slot', (children: React.ReactNode, extra = {}) => (
    <FilamentHoverCard
      data={baseFilamentData}
      slotLabel="AMS A Slot 2"
      configureSlot={{ enabled: true, onConfigure: vi.fn() }}
      {...extra}
    >
      {children}
    </FilamentHoverCard>
  )],
  ['EmptySlotHoverCard', 'empty-slot', (children: React.ReactNode, extra = {}) => (
    <EmptySlotHoverCard
      slotLabel="AMS A Slot 2"
      configureSlot={{ enabled: true, onConfigure: vi.fn() }}
      {...extra}
    >
      {children}
    </EmptySlotHoverCard>
  )],
])('%s as a tap target (#3577)', (_name, testId, build) => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  const configureButton = () => screen.queryByRole('button', { name: /^configure$/i });

  it('is a focusable, named button that reports its state', () => {
    render(build(<span>PLA</span>));
    const tile = screen.getByTestId(testId);
    expect(tile).toHaveAttribute('role', 'button');
    expect(tile).toHaveAttribute('tabindex', '0');
    expect(tile.getAttribute('aria-label')).toMatch(/^AMS A Slot 2 - .+/);
    expect(tile).toHaveAttribute('aria-expanded', 'false');
    expect(tile).not.toHaveAttribute('aria-controls');
  });

  it('opens on a click and closes on the second click', () => {
    render(build(<span>PLA</span>));
    const tile = screen.getByTestId(testId);
    fireEvent.click(screen.getByText('PLA'));
    expect(configureButton()).toBeInTheDocument();
    expect(tile).toHaveAttribute('aria-expanded', 'true');
    const cardId = tile.getAttribute('aria-controls')!;
    expect(document.getElementById(cardId)).toContainElement(configureButton());
    fireEvent.click(screen.getByText('PLA'));
    expect(configureButton()).not.toBeInTheDocument();
    expect(tile).toHaveAttribute('aria-expanded', 'false');
  });

  it('opens on Enter and on Space, and Space does not scroll the page', () => {
    render(build(<span>PLA</span>));
    const tile = screen.getByTestId(testId);
    tile.focus();
    fireEvent.keyDown(tile, { key: 'Enter' });
    expect(configureButton()).toBeInTheDocument();
    fireEvent.keyDown(tile, { key: 'Enter' });
    expect(configureButton()).not.toBeInTheDocument();
    const notPrevented = fireEvent.keyDown(tile, { key: ' ' });
    expect(notPrevented).toBe(false);
    expect(configureButton()).toBeInTheDocument();
  });

  it('closes on Escape and returns focus to the tile', () => {
    render(build(<span>PLA</span>));
    const tile = screen.getByTestId(testId);
    fireEvent.click(tile);
    // Focus sits on the card's own button, as after a click inside it.
    configureButton()!.focus();
    fireEvent.keyDown(configureButton()!, { key: 'Escape' });
    expect(configureButton()).not.toBeInTheDocument();
    expect(tile).toHaveFocus();
  });

  it('closes on a press outside the tile and the card', () => {
    render(build(<span>PLA</span>));
    fireEvent.click(screen.getByTestId(testId));
    fireEvent.pointerDown(configureButton()!);
    expect(configureButton()).toBeInTheDocument();
    fireEvent.pointerDown(document.body);
    expect(configureButton()).not.toBeInTheDocument();
  });

  it('does not toggle the tile when a button inside the card is clicked', () => {
    const onConfigure = vi.fn();
    render(build(<span>PLA</span>, { configureSlot: { enabled: true, onConfigure } }));
    fireEvent.click(screen.getByTestId(testId));
    fireEvent.click(configureButton()!);
    expect(onConfigure).toHaveBeenCalledTimes(1);
    // The action dismisses the card itself; it must not be re-opened by the
    // click bubbling to the tile.
    expect(configureButton()).not.toBeInTheDocument();
  });

  it('ignores Enter and Space typed on a control inside the card', () => {
    render(build(<span>PLA</span>));
    fireEvent.click(screen.getByTestId(testId));
    fireEvent.keyDown(configureButton()!, { key: 'Enter' });
    expect(configureButton()).toBeInTheDocument();
  });

  it('does not double-toggle on the emulated mouse events after a touch tap', () => {
    render(build(<span>PLA</span>));
    const tile = screen.getByTestId(testId);
    // What a browser sends for one tap, in order.
    pointer(tile, 'pointerEnter', 'touch');
    pointer(tile, 'pointerDown', 'touch');
    fireEvent.mouseEnter(tile);
    advance(200);
    expect(configureButton()).not.toBeInTheDocument();
    fireEvent.click(tile);
    expect(configureButton()).toBeInTheDocument();
    // A late emulated mouseleave must not close it either.
    fireEvent.mouseLeave(tile);
    advance(200);
    expect(configureButton()).toBeInTheDocument();
    // Second tap closes it.
    pointer(tile, 'pointerDown', 'touch');
    fireEvent.mouseEnter(tile);
    advance(200);
    fireEvent.click(tile);
    expect(configureButton()).not.toBeInTheDocument();
  });

  it('keeps real mouse hover working once the touch window has passed', () => {
    render(build(<span>PLA</span>));
    const tile = screen.getByTestId(testId);
    pointer(tile, 'pointerDown', 'touch');
    advance(1500);
    fireEvent.mouseEnter(tile);
    advance(100);
    expect(configureButton()).toBeInTheDocument();
    fireEvent.mouseLeave(tile);
    advance(150);
    expect(configureButton()).not.toBeInTheDocument();
  });

  it('does not close a hover-opened card on a mouse click', () => {
    render(build(<span>PLA</span>));
    const tile = screen.getByTestId(testId);
    fireEvent.mouseEnter(tile);
    advance(100);
    pointer(tile, 'pointerDown', 'mouse');
    fireEvent.click(tile);
    expect(configureButton()).toBeInTheDocument();
  });

  it('keeps a hover-opened card open on a pen tap', () => {
    render(build(<span>PLA</span>));
    const tile = screen.getByTestId(testId);
    fireEvent.mouseEnter(tile);
    advance(100);
    pointer(tile, 'pointerDown', 'pen');
    fireEvent.click(tile);
    expect(configureButton()).toBeInTheDocument();
    // A second pen tap is a real toggle.
    pointer(tile, 'pointerDown', 'pen');
    fireEvent.click(tile);
    expect(configureButton()).not.toBeInTheDocument();
  });

  it('closes on Escape pressed anywhere in the document', () => {
    render(build(<span>PLA</span>));
    fireEvent.click(screen.getByTestId(testId));
    const outside = document.createElement('button');
    document.body.appendChild(outside);
    outside.focus();
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(configureButton()).not.toBeInTheDocument();
    expect(outside).toHaveFocus();
    outside.remove();
  });

  it('closes when focus moves outside the tile and the card', () => {
    render(build(<span>PLA</span>));
    const tile = screen.getByTestId(testId);
    tile.focus();
    fireEvent.keyDown(tile, { key: 'Enter' });
    expect(configureButton()).toBeInTheDocument();
    act(() => configureButton()!.focus());
    expect(configureButton()).toBeInTheDocument();
    const outside = document.createElement('button');
    document.body.appendChild(outside);
    act(() => outside.focus());
    expect(screen.queryByRole('button', { name: /^configure$/i })).not.toBeInTheDocument();
    outside.remove();
  });

  it('does not throw when unmounted with a pending show timer', () => {
    const { unmount } = render(build(<span>PLA</span>));
    fireEvent.mouseEnter(screen.getByTestId(testId));
    unmount();
    expect(() => advance(500)).not.toThrow();
    expect(configureButton()).not.toBeInTheDocument();
  });

  it('keeps the card text selectable although the tile is not', () => {
    render(build(<span>PLA</span>));
    fireEvent.click(screen.getByTestId(testId));
    const card = document.getElementById(screen.getByTestId(testId).getAttribute('aria-controls')!)!;
    expect(card).toHaveClass('select-text');
    expect(screen.getByTestId(testId)).not.toContainElement(card);
  });
});

describe('only one slot card is open at a time (#3577)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  const renderTwo = () =>
    render(
      <>
        <FilamentHoverCard data={baseFilamentData} slotLabel="Slot A" configureSlot={{ enabled: true, onConfigure: vi.fn() }}>
          <span>A</span>
        </FilamentHoverCard>
        <FilamentHoverCard data={baseFilamentData} slotLabel="Slot B" configureSlot={{ enabled: true, onConfigure: vi.fn() }}>
          <span>B</span>
        </FilamentHoverCard>
      </>
    );
  const tiles = () => screen.getAllByTestId('filament-slot');
  const cards = () => screen.queryAllByRole('button', { name: /^configure$/i });

  it('opening B by click closes A', () => {
    renderTwo();
    fireEvent.click(tiles()[0]);
    expect(cards()).toHaveLength(1);
    fireEvent.click(tiles()[1]);
    expect(cards()).toHaveLength(1);
    expect(tiles()[0]).toHaveAttribute('aria-expanded', 'false');
    expect(tiles()[1]).toHaveAttribute('aria-expanded', 'true');
  });

  it('opening B by keyboard closes A', () => {
    renderTwo();
    tiles()[0].focus();
    fireEvent.keyDown(tiles()[0], { key: 'Enter' });
    tiles()[1].focus();
    fireEvent.keyDown(tiles()[1], { key: ' ' });
    expect(cards()).toHaveLength(1);
    expect(tiles()[0]).toHaveAttribute('aria-expanded', 'false');
    expect(tiles()[1]).toHaveAttribute('aria-expanded', 'true');
  });
});

describe('FilamentHoverCard disabled tile (#3577)', () => {
  it('stays inert: not focusable, no toggling, aria-disabled', () => {
    render(
      <FilamentHoverCard data={baseFilamentData} disabled>
        <span>PLA</span>
      </FilamentHoverCard>
    );
    const tile = screen.getByTestId('filament-slot');
    expect(tile).toHaveAttribute('aria-disabled', 'true');
    expect(tile).not.toHaveAttribute('tabindex');
    expect(tile).not.toHaveAttribute('aria-expanded');
    fireEvent.click(tile);
    fireEvent.keyDown(tile, { key: 'Enter' });
    expect(screen.queryByText('PLA Basic')).not.toBeInTheDocument();
  });
});
