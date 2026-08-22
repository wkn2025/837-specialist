/**
 * Field-level helpers shared by the form and its hook.
 *
 * Money is handled in integer cents, never in floating point: the generator
 * rounds the 837I split with Decimal/ROUND_HALF_UP (overrides.py), and a
 * float here would disagree with it on some charges - the exact bug task 6
 * had to fix inside validate.py.
 */

/** Cents for "446.00" / "446" / "" -> null when it is not a money value. */
export function cents(raw: string): number | null {
  const s = raw.trim();
  if (!/^-?\d+(\.\d{1,2})?$/.test(s)) return null;
  const neg = s.startsWith('-');
  const [whole, frac = ''] = s.replace('-', '').split('.');
  const v = Number(whole) * 100 + Number(frac.padEnd(2, '0'));
  return neg ? -v : v;
}

export function money(c: number): string {
  const sign = c < 0 ? '-' : '';
  const a = Math.abs(c);
  return `${sign}${Math.floor(a / 100)}.${String(a % 100).padStart(2, '0')}`;
}

/**
 * The 837I savings, half-up on 15% of billed - the same arithmetic
 * overrides.py does, mirrored here only so the read-only column can show
 * the number before the generator runs. The generator still owns the rule;
 * this never travels in an override document.
 */
export function derivedSavings(billed: string): string {
  const c = cents(billed);
  // A negative charge is refused by the generator (overrides._money), so
  // there is no split to show for one.
  if (c === null || c < 0) return '';
  return money(Math.floor((c * 15 + 50) / 100));
}

/** Billed - Savings, blank when either side is not a money value. */
export function allowed(billed: string, savings: string): string {
  const b = cents(billed);
  const s = cents(savings);
  return b === null || s === null ? '' : money(b - s);
}

/** CCYYMMDD -> MM/DD/YYYY for display; anything else passes through. */
export function showDate(d: string): string {
  return /^\d{8}$/.test(d)
    ? `${d.slice(4, 6)}/${d.slice(6, 8)}/${d.slice(0, 4)}`
    : d;
}

/** MM/DD/YYYY -> CCYYMMDD; anything else passes through unchanged. */
export function parseDate(v: string): string {
  const m = v.trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  return m
    ? `${m[3]}${m[1].padStart(2, '0')}${m[2].padStart(2, '0')}`
    : v.trim();
}
