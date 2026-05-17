/**
 * EMU (English Metric Unit) conversion utilities.
 *
 * 1 inch      = 914,400 EMU
 * Slide width = 9,144,000 EMU  (10 in)
 * Slide height= 5,143,500 EMU  (5.625 in, 16:9)
 * Font size   : EMU / 12,700 → points; points × 0.75 → px
 */

export const SLIDE_WIDTH_EMU  = 9_144_000;
export const SLIDE_HEIGHT_EMU = 5_143_500;

/**
 * Converts an EMU value to a CSS percentage string relative to `totalEmu`.
 *
 * @param emu      - The EMU value to convert (position or dimension).
 * @param totalEmu - The total slide dimension in EMU (width or height).
 * @returns A percentage string, e.g. `"42.5%"`.
 */
export function emuToPercent(emu: number, totalEmu: number): string {
  if (totalEmu === 0) return '0%';
  return `${((emu / totalEmu) * 100).toFixed(4)}%`;
}

/**
 * Converts a font size stored in EMU (python-pptx format) to CSS pixels.
 * Formula: EMU / 12700 → points → × 0.75 → px
 *
 * @param fontSizeEmu - Font size in EMU.
 * @returns CSS pixel value as a number (caller appends "px").
 */
export function emuFontSizeToPx(fontSizeEmu: number): number {
  const points = fontSizeEmu / 12_700;
  return points * 0.75;
}
