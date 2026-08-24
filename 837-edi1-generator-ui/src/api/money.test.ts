// @vitest-environment node
/**
 * Task 11: the 837I savings/allowed shown in the form are derived in the
 * browser, so they are pinned to the Python functions that actually write
 * them rather than to a hand-written table.
 */
import { describe, expect, it } from 'vitest';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { findRepo } from '../../server/api.js';
import { allowedFrom, derivedAllowed, derivedSavings, roundPy, total }
  from './money.js';

const REPO = findRepo();
const SCRIPTS = path.join(REPO, 'skill/generating-uhcg-edi-files/scripts');

/** What overrides.py really returns, for the same inputs. */
function python(values: string[]): Array<[string, string]> {
  const src = [
    'import json, sys',
    `sys.path.insert(0, ${JSON.stringify(SCRIPTS)})`,
    'import overrides',
    'vals = json.load(sys.stdin)',
    'print(json.dumps([[str(overrides.derived_savings(v)),',
    '                   str(overrides.derived_allowed(v))] for v in vals]))',
  ].join('\n');
  const out = execFileSync(process.env.PYTHON ?? 'python', ['-c', src], {
    input: JSON.stringify(values),
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  });
  return JSON.parse(out);
}

describe('derived amounts match the generator', () => {
  it('agrees with Python across the whole cent range it will ever see', () => {
    const values: string[] = [];
    for (let cents = 1; cents <= 40000; cents += 1) {
      values.push((cents / 100).toFixed(2));
    }
    const expected = python(values);
    const mismatches: string[] = [];
    values.forEach((v, i) => {
      const [savings, allowed] = expected[i];
      if (derivedSavings(v) !== savings) {
        mismatches.push(`savings ${v}: python ${savings}, ui ${derivedSavings(v)}`);
      }
      if (derivedAllowed(v) !== allowed) {
        mismatches.push(`allowed ${v}: python ${allowed}, ui ${derivedAllowed(v)}`);
      }
    });
    expect(mismatches.slice(0, 10)).toEqual([]);
  }, 120_000);

  it('agrees on the exact ties that half-up rounding gets wrong', () => {
    // 2.50 * 0.85 = 2.125 exactly; Python rounds half to even.
    expect(derivedAllowed('2.50')).toBe('2.12');
    expect((2.5 * 0.85).toFixed(2)).toBe('2.13');
    expect(derivedSavings('7.50')).toBe('1.12');
  });
});

describe('roundPy', () => {
  it('leaves a non-tie to the ordinary rounding', () => {
    expect(roundPy(1.005)).toBe('1.00');   // the double is 1.00499...
    expect(roundPy(0.125)).toBe('0.12');   // an exact tie, rounds to even
    expect(roundPy(0.135)).toBe('0.14');   // the double is 0.13500000000000001
  });

  it('keeps the sign of a negative tie', () => {
    expect(roundPy(-0.125)).toBe('-0.12');
  });
});

describe('presentational helpers', () => {
  it('computes 837P allowed as billed minus a freely chosen savings', () => {
    expect(allowedFrom('446.00', '174.35')).toBe('271.65');
  });

  it('treats a blank savings as nothing withheld', () => {
    expect(allowedFrom('100.00', '')).toBe('100.00');
  });

  it('returns nothing at all for a blank billed', () => {
    expect(derivedSavings('')).toBe('');
    expect(allowedFrom('', '5.00')).toBe('');
  });

  it('totals a column', () => {
    expect(total(['446.00', '159.00', ''])).toBe('605.00');
  });
});
