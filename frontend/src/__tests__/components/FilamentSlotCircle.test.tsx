/**
 * Tests for the FilamentSlotCircle component.
 */

import { describe, it, expect } from 'vitest';
import type React from 'react';
import { screen } from '@testing-library/react';
import { render } from '../utils';
import { FilamentSlotCircle } from '../../components/FilamentSlotCircle';

/**
 * JSDOM normalizes some CSS color values (e.g. #000 → rgb(0, 0, 0)),
 * so we compare against both hex and rgb forms.
 */
function expectColor(actual: string, hex: string, rgb: string) {
  expect([hex, rgb]).toContain(actual);
}

describe('FilamentSlotCircle', () => {
  it('renders the slot number', () => {
    render(<FilamentSlotCircle trayColor="FF0000" trayType="PLA" isEmpty={false} slotNumber={1} />);
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('renders slot number for empty slot', () => {
    render(<FilamentSlotCircle isEmpty={true} slotNumber={3} />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('uses dashed border for empty slots', () => {
    const { container } = render(
      <FilamentSlotCircle isEmpty={true} slotNumber={1} />
    );
    const circle = container.firstChild as HTMLElement;
    expect(circle.style.borderStyle).toBe('dashed');
  });

  it('uses solid border for filled slots', () => {
    const { container } = render(
      <FilamentSlotCircle trayColor="FF0000" isEmpty={false} slotNumber={1} />
    );
    const circle = container.firstChild as HTMLElement;
    expect(circle.style.borderStyle).toBe('solid');
  });

  it('sets background color from trayColor', () => {
    const { container } = render(
      <FilamentSlotCircle trayColor="00FF00" trayType="PLA" isEmpty={false} slotNumber={2} />
    );
    const circle = container.firstChild as HTMLElement;
    expectColor(circle.style.backgroundColor, '#00FF00', 'rgb(0, 255, 0)');
  });

  it('uses dark background when trayType is set but no color', () => {
    const { container } = render(
      <FilamentSlotCircle trayType="PLA" isEmpty={false} slotNumber={1} />
    );
    const circle = container.firstChild as HTMLElement;
    expectColor(circle.style.backgroundColor, '#333', 'rgb(51, 51, 51)');
  });

  it('uses transparent background when empty and no type', () => {
    const { container } = render(
      <FilamentSlotCircle isEmpty={true} slotNumber={1} />
    );
    const circle = container.firstChild as HTMLElement;
    expect(circle.style.backgroundColor).toBe('transparent');
  });

  it('uses black text on light filament colors', () => {
    // White filament (FFFFFF) is light
    render(<FilamentSlotCircle trayColor="FFFFFF" isEmpty={false} slotNumber={1} />);
    const text = screen.getByText('1');
    expectColor(text.style.color, '#000', 'rgb(0, 0, 0)');
  });

  it('uses white text on dark filament colors', () => {
    // Black filament (000000) is dark
    render(<FilamentSlotCircle trayColor="000000" isEmpty={false} slotNumber={1} />);
    const text = screen.getByText('1');
    expectColor(text.style.color, '#fff', 'rgb(255, 255, 255)');
  });

  it('uses white text when no tray color', () => {
    render(<FilamentSlotCircle isEmpty={true} slotNumber={1} />);
    const text = screen.getByText('1');
    expectColor(text.style.color, '#fff', 'rgb(255, 255, 255)');
  });

  it('draws exactly what it did before when none of the picture props is set', () => {
    // The printer card (PrintersPage) must not change: the markup is the one it always had.
    const draw = (node: React.ReactElement) => render(node).container.firstElementChild?.outerHTML;
    expect(draw(<FilamentSlotCircle trayColor="FF0000" trayType="PLA" isEmpty={false} slotNumber={1} />)).toBe(
      '<div class="w-3.5 h-3.5 rounded-full mx-auto mb-0.5 border-2 flex items-center justify-center" style="background-color: rgb(255, 0, 0); border-color: rgba(255, 255, 255, 0.1); border-style: solid;"><span class="text-[6px] font-bold leading-none select-none" style="color: rgb(255, 255, 255);">1</span></div>',
    );
    expect(draw(<FilamentSlotCircle isEmpty emptyKind="reset" slotNumber={3} />)).toBe(
      '<div class="w-3.5 h-3.5 rounded-full mx-auto mb-0.5 border-2 flex items-center justify-center" style="background-color: transparent; border-color: rgb(61, 61, 61); border-style: dashed;"><span class="text-[6px] font-bold leading-none select-none" style="color: rgb(255, 255, 255);">3</span></div>',
    );
    expect(draw(<FilamentSlotCircle isEmpty pendingColor="00FF00FF" trayType="PLA" slotNumber="L" />)).toBe(
      '<div class="w-3.5 h-3.5 rounded-full mx-auto mb-0.5 border-2 flex items-center justify-center" data-pending-config="true" style="background-color: rgb(0, 255, 0); border-color: rgb(245, 158, 11); border-style: dashed;"><span class="text-[6px] font-bold leading-none select-none" style="color: rgb(255, 255, 255);">L</span></div>',
    );
  });

  describe('looks of a spool (the To do picture)', () => {
    const circle = (container: HTMLElement) => container.firstElementChild as HTMLElement;

    it('draws a multicolour spool as segments, conic for Multicolor, linear otherwise', () => {
      const { container, unmount } = render(
        <FilamentSlotCircle isEmpty={false} slotNumber={1} rgba="FF0000FF" extraColors="ec984c,6cd4bc,a66eb9" subtype="Multicolor" />,
      );
      expect(circle(container).style.backgroundImage.toLowerCase()).toMatch(/conic-gradient/);
      expect(circle(container).style.backgroundColor).toBe('');
      unmount();
      const linear = render(<FilamentSlotCircle isEmpty={false} slotNumber={1} rgba="FF0000FF" extraColors="ec984c,6cd4bc" />);
      const bg = circle(linear.container).style.backgroundImage.toLowerCase();
      expect(bg).toMatch(/linear-gradient/);
      expect(bg).toContain('#ec984c');
      expect(bg).toContain('#6cd4bc');
    });

    it('keeps the alpha of a translucent spool over the checkerboard', () => {
      const { container } = render(<FilamentSlotCircle isEmpty={false} slotNumber={1} rgba="FFFFFF40" />);
      const bg = circle(container).style.backgroundImage.toLowerCase();
      expect(bg).toContain('#ffffff40');
      expect(bg).toContain('conic-gradient');
    });

    it('takes the number colour from the spool: black on a light one, white on a dark one', () => {
      const light = render(<FilamentSlotCircle isEmpty={false} slotNumber={2} rgba="F4EFEBFF" />);
      expectColor(screen.getByText('2').style.color, '#000', 'rgb(0, 0, 0)');
      light.unmount();
      render(<FilamentSlotCircle isEmpty={false} slotNumber={2} rgba="101010FF" />);
      expectColor(screen.getByText('2').style.color, '#fff', 'rgb(255, 255, 255)');
    });

    it('still draws an empty slot dashed and without colour when it is given looks', () => {
      const { container } = render(<FilamentSlotCircle isEmpty slotNumber={4} rgba="C8102EFF" />);
      expect(circle(container).style.borderStyle).toBe('dashed');
      expect(circle(container).style.backgroundImage).toBe('');
      expect(circle(container).style.backgroundColor).toBe('transparent');
    });

    it('takes its size, number size, extra classes, border and title from the caller', () => {
      const { container } = render(
        <FilamentSlotCircle isEmpty={false} slotNumber={1} rgba="C8102EFF" sizeClass="w-[30px] h-[30px]" numberClass="text-xs" className="opacity-50" borderColor="#123456" title="Lava Red" />,
      );
      const el = circle(container);
      expect(el.className).toContain('w-[30px] h-[30px]');
      expect(el.className).not.toContain('w-3.5');
      expect(el.className).toContain('opacity-50');
      expect(screen.getByText('1').className).toContain('text-xs');
      expectColor(el.style.borderColor, '#123456', 'rgb(18, 52, 86)');
      expect(el).toHaveAttribute('title', 'Lava Red');
    });

    it('draws no number for an empty slotNumber', () => {
      const { container } = render(<FilamentSlotCircle isEmpty={false} slotNumber="" rgba="C8102EFF" />);
      expect(circle(container).querySelector('span')).toBeNull();
    });
  });
});
