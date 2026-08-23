/**
 * Display-only mirrors of the generator's derived amounts.
 *
 * The authority is overrides.derived_savings/derived_allowed in
 * skill/generating-uhcg-edi-files/scripts/overrides.py, which compute
 * `round(float(billed) * 0.15, 2)` and `round(float(billed) * 0.85, 2)`.
 * The 837I savings column is read-only precisely because the generator owns
 * it, so the browser must never send these values - it only shows them, and
 * showing a different number than the file will carry would be a lie.
 *
 * IEEE754 doubles are the same in both languages, so the product is bit
 * identical; only the rounding differs. Number.toFixed rounds half away from
 * zero, Python's round() rounds half to even, and the two disagree on the
 * exact ties (2.50 * 0.85 = 2.125 -> 2.12 in Python, 2.13 via toFixed).
 * roundPy reproduces Python's answer. src/api/money.test.ts proves the
 * agreement against the real Python functions.
 */

/** `round(x, 2)` exactly as CPython does it, for a double x. */
export function roundPy(x: number): string {
  const exact = x.toFixed(20);
  const point = exact.indexOf('.');
  const tail = exact.slice(point + 3);
  // A double that is an exact tie at 2dp has at most 3 decimal digits, so its
  // expansion here is a lone 5 followed by zeros. Anything else is not a tie
  // and toFixed already rounds it the way Python does.
  if (!/^50*$/.test(tail)) return x.toFixed(2);
  const cents = Number(exact.slice(0, point) + exact.slice(point + 1, point + 3));
  const even = cents % 2 === 0 ? cents : cents + (x < 0 ? -1 : 1);
  return (even / 100).toFixed(2);
}

function amount(billed: string, factor: number): string {
  const n = Number(billed);
  if (billed.trim() === '' || !Number.isFinite(n)) return '';
  return roundPy(n * factor);
}

/** 837I: the savings the generator will write, 15% of the charge. */
export const derivedSavings = (billed: string): string => amount(billed, 0.15);

/** 837I: the allowed amount, 85% of the charge - not billed minus savings. */
export const derivedAllowed = (billed: string): string => amount(billed, 0.85);

/** 837P: allowed is what is left after a freely chosen savings. */
export function allowedFrom(billed: string, savings: string): string {
  const b = Number(billed);
  const s = Number(savings);
  if (!Number.isFinite(b) || !Number.isFinite(s)) return '';
  if (billed.trim() === '') return '';
  return roundPy(b - (savings.trim() === '' ? 0 : s));
}

/** Sum a column of amount strings, blanks counting as nothing. */
export function total(values: string[]): string {
  let sum = 0;
  for (const v of values) {
    const n = Number(v);
    if (v.trim() !== '' && Number.isFinite(n)) sum += n;
  }
  return roundPy(sum);
}
