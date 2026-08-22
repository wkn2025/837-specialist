/**
 * The New Batch form's state.
 *
 * Two rules shape everything here:
 *
 * 1. Defaults are never hand-written. They arrive from GET /api/defaults,
 *    which reads the real seed - so a seed change can never silently
 *    disagree with what the form shows.
 * 2. toDocument() emits ONLY what the user actually edited. The generator
 *    freezes every byte the override document does not declare, so
 *    declaring an untouched field would trade a frozen-identity check for
 *    nothing. A field the user never touched must stay undeclared.
 */
import { useCallback, useEffect, useMemo, useReducer } from 'react';
import type {
  ClaimDoc, DefaultsDoc, GeneratedBatch, Identity, IdentityGroup, Line,
  OverrideDoc, TxType,
} from '@/api/types';
import { cents } from '@/lib/fields';

export interface FormState {
  type: TxType;
  claims: number;
  identity: Identity;
  claimDocs: ClaimDoc[];
  expanded: Set<number>;
  generated: boolean;
  result: GeneratedBatch | null;
}

/** Which fields the user has touched, per group and per claim. */
interface Edits {
  identity: Record<string, Set<string>>;
  claims: Record<number, { diagnosis: boolean; lines: boolean }>;
}

interface State extends FormState {
  seed: DefaultsDoc | null;
  edits: Edits;
  loaded: boolean;
  error: string | null;
}

const EMPTY_IDENTITY: Identity = {
  subscriber: { last: '', first: '', memberId: '', dob: '' },
  billingProvider: { name: '', npi: '' },
};

const INITIAL: State = {
  type: 'I',
  claims: 1,
  identity: EMPTY_IDENTITY,
  claimDocs: [],
  expanded: new Set(),
  generated: false,
  result: null,
  seed: null,
  edits: { identity: {}, claims: {} },
  loaded: false,
  error: null,
};

/**
 * Claim n takes seed block ((n-1) % blocks)+1 - generate.py's source_index,
 * mirrored so the form shows the same block the file will be built from.
 */
function cycle(seed: ClaimDoc[], count: number, from = 0): ClaimDoc[] {
  return Array.from({ length: count - from }, (_, k) => {
    const n = from + k;
    const src = seed[n % seed.length];
    return {
      n: n + 1,
      principalDiagnosis: src.principalDiagnosis ?? '',
      lines: src.lines.map((l) => ({ ...l })),
    };
  });
}

type Action =
  | { t: 'loaded'; doc: DefaultsDoc }
  | { t: 'error'; message: string }
  | { t: 'type'; type: TxType }
  | { t: 'claims'; claims: number }
  | { t: 'identity'; group: IdentityGroup; field: string; value: string }
  | { t: 'diagnosis'; n: number; value: string }
  | { t: 'line'; n: number; i: number; field: keyof Line; value: string }
  | { t: 'addLine'; n: number }
  | { t: 'removeLine'; n: number; i: number }
  | { t: 'toggle'; n: number }
  | { t: 'generated'; result: GeneratedBatch };

/** Every edit invalidates a generated batch; only 'generated' sets it. */
function edited(s: State): State {
  return s.generated ? { ...s, generated: false } : s;
}

function markClaim(edits: Edits, n: number,
                   what: 'diagnosis' | 'lines'): Edits {
  const prev = edits.claims[n] ?? { diagnosis: false, lines: false };
  return {
    ...edits,
    claims: { ...edits.claims, [n]: { ...prev, [what]: true } },
  };
}

function withClaim(s: State, n: number, next: (c: ClaimDoc) => ClaimDoc) {
  return s.claimDocs.map((c) => (c.n === n ? next(c) : c));
}

function reduce(s: State, a: Action): State {
  switch (a.t) {
    case 'loaded':
      // The seed's own claim count is the form's starting batch size, so an
      // untouched form is exactly the seed.
      return {
        ...s,
        seed: a.doc,
        identity: a.doc.identity,
        claims: a.doc.claims.length,
        claimDocs: cycle(a.doc.claims, a.doc.claims.length),
        edits: { identity: {}, claims: {} },
        expanded: new Set(),
        generated: false,
        result: null,
        loaded: true,
        error: null,
      };

    case 'error':
      return { ...s, loaded: false, error: a.message };

    case 'type':
      // A new seed is a new set of defaults; the effect refetches and
      // 'loaded' rebuilds everything. Edits against the old seed cannot
      // survive, because the fields they named belong to a different file.
      return a.type === s.type ? s : { ...INITIAL, type: a.type };

    case 'claims': {
      if (!s.seed || a.claims === s.claims) return s;
      const grow = a.claims > s.claimDocs.length;
      // Shrinking drops the tail's edits with the claims themselves; a
      // claim that is not in the batch has nothing to declare.
      const claimEdits = grow
        ? s.edits.claims
        : Object.fromEntries(Object.entries(s.edits.claims)
          .filter(([n]) => Number(n) <= a.claims));
      return edited({
        ...s,
        claims: a.claims,
        claimDocs: grow
          ? [...s.claimDocs,
            ...cycle(s.seed.claims, a.claims, s.claimDocs.length)]
          : s.claimDocs.slice(0, a.claims),
        edits: { ...s.edits, claims: claimEdits },
        expanded: new Set([...s.expanded].filter((n) => n <= a.claims)),
      });
    }

    case 'identity': {
      const fields = new Set(s.edits.identity[a.group] ?? []);
      fields.add(a.field);
      const group = a.group === 'taxId'
        ? a.value
        : { ...(s.identity[a.group] as object), [a.field]: a.value };
      return edited({
        ...s,
        identity: { ...s.identity, [a.group]: group },
        edits: {
          ...s.edits,
          identity: { ...s.edits.identity, [a.group]: fields },
        },
      });
    }

    case 'diagnosis':
      return edited({
        ...s,
        claimDocs: withClaim(s, a.n,
          (c) => ({ ...c, principalDiagnosis: a.value })),
        edits: markClaim(s.edits, a.n, 'diagnosis'),
      });

    case 'line':
      return edited({
        ...s,
        claimDocs: withClaim(s, a.n, (c) => ({
          ...c,
          lines: c.lines.map((l, i) =>
            (i === a.i ? { ...l, [a.field]: a.value } : l)),
        })),
        edits: markClaim(s.edits, a.n, 'lines'),
      });

    case 'addLine':
      return edited({
        ...s,
        claimDocs: withClaim(s, a.n, (c) => ({
          ...c,
          // A new line starts on the last line's date with no amounts, so
          // canGenerate keeps the button gray until they are filled in.
          lines: [...c.lines, {
            date: c.lines[c.lines.length - 1]?.date ?? '',
            billed: '',
            savings: '',
          }],
        })),
        edits: markClaim(s.edits, a.n, 'lines'),
      });

    case 'removeLine':
      return edited({
        ...s,
        claimDocs: withClaim(s, a.n, (c) => (c.lines.length < 2 ? c : {
          ...c,
          lines: c.lines.filter((_, i) => i !== a.i),
        })),
        edits: markClaim(s.edits, a.n, 'lines'),
      });

    case 'toggle': {
      const expanded = new Set(s.expanded);
      if (!expanded.delete(a.n)) expanded.add(a.n);
      // Collapsing is not an edit - it changes nothing the file is built
      // from, so it must not invalidate a generated batch.
      return { ...s, expanded };
    }

    case 'generated':
      return { ...s, generated: true, result: a.result };
  }
}

function filled(v: unknown): boolean {
  return typeof v === 'string' && v.trim() !== '';
}

function lineOk(l: Line, type: TxType): boolean {
  if (!/^\d{8}$/.test(l.date)) return false;
  const b = cents(l.billed);
  if (b === null || b < 0) return false;
  if (type === 'I') return true;
  // 837P: overrides.parse requires a savings per line and refuses one that
  // exceeds the charge.
  const sv = cents(l.savings);
  return sv !== null && sv >= 0 && sv <= b;
}

export function useBatchForm(fetcher: typeof fetch = fetch) {
  const [s, dispatch] = useReducer(reduce, INITIAL);

  useEffect(() => {
    let live = true;
    fetcher(`/api/defaults?type=${s.type}`)
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body?.error ?? r.statusText);
        return body as DefaultsDoc;
      })
      .then((doc) => { if (live) dispatch({ t: 'loaded', doc }); })
      .catch((e: Error) => {
        if (live) dispatch({ t: 'error', message: e.message });
      });
    return () => { live = false; };
  }, [s.type, fetcher]);

  const form: FormState = s;

  const canGenerate = useMemo(() => {
    if (!s.loaded || s.claimDocs.length !== s.claims) return false;
    const { subscriber, billingProvider, attendingProvider } = s.identity;
    const people = [subscriber, billingProvider, attendingProvider]
      .filter(Boolean) as object[];
    // taxId is left out on purpose: a seed without a REF*EI has none, and
    // the form must not demand a field the file does not carry.
    if (!people.every((p) => Object.values(p).every(filled))) return false;
    return s.claimDocs.every((c) =>
      filled(c.principalDiagnosis)
      && c.lines.length > 0
      && c.lines.every((l) => lineOk(l, s.type)));
  }, [s.loaded, s.claims, s.claimDocs, s.identity, s.type]);

  const editedGroups = useMemo(() => new Set(
    Object.entries(s.edits.identity)
      .filter(([, fields]) => fields.size > 0)
      .map(([group]) => group),
  ), [s.edits.identity]);

  const toDocument = useCallback((): OverrideDoc => {
    const identity: Record<string, unknown> = {};
    for (const [group, fields] of Object.entries(s.edits.identity)) {
      if (fields.size === 0) continue;
      if (group === 'taxId') {
        identity.taxId = s.identity.taxId;
        continue;
      }
      const src = s.identity[group as IdentityGroup] as unknown as
        Record<string, string> | undefined;
      // Only the touched fields: an untouched sibling stays frozen against
      // the seed rather than becoming a declaration that says the same
      // thing.
      identity[group] = Object.fromEntries(
        [...fields].map((f) => [f, src?.[f] ?? '']));
    }

    const claims: OverrideDoc['claims'] = [];
    for (const c of s.claimDocs) {
      const e = s.edits.claims[c.n];
      if (!e || (!e.diagnosis && !e.lines)) continue;
      const entry: OverrideDoc['claims'][number] = { n: c.n };
      if (e.diagnosis) entry.principalDiagnosis = c.principalDiagnosis;
      if (e.lines) {
        // Lines are declared as a whole set - splice_lines sizes the claim's
        // LX loops to this array - so an edited claim sends all of its
        // lines, not only the row that changed.
        entry.lines = c.lines.map((l) => (s.type === 'I'
          // 837I savings is the 85/15 split of billed. The generator derives
          // it and refuses a value that disagrees, so sending one at all
          // would only ever be redundant or wrong.
          ? { date: l.date, billed: l.billed }
          : { date: l.date, billed: l.billed, savings: l.savings }));
      }
      claims.push(entry);
    }
    return { identity, claims };
  }, [s.claimDocs, s.edits, s.identity, s.type]);

  return {
    form,
    loaded: s.loaded,
    error: s.error,
    canGenerate,
    editedGroups,
    editedClaims: s.edits.claims,
    setType: useCallback((type: TxType) => dispatch({ t: 'type', type }), []),
    setClaims: useCallback(
      (claims: number) => dispatch({ t: 'claims', claims }), []),
    updateIdentity: useCallback(
      (group: IdentityGroup, field: string, value: string) =>
        dispatch({ t: 'identity', group, field, value }), []),
    updateDiagnosis: useCallback(
      (n: number, value: string) => dispatch({ t: 'diagnosis', n, value }), []),
    updateLine: useCallback(
      (n: number, i: number, field: keyof Line, value: string) =>
        dispatch({ t: 'line', n, i, field, value }), []),
    addLine: useCallback((n: number) => dispatch({ t: 'addLine', n }), []),
    removeLine: useCallback(
      (n: number, i: number) => dispatch({ t: 'removeLine', n, i }), []),
    toggleExpanded: useCallback((n: number) => dispatch({ t: 'toggle', n }), []),
    markGenerated: useCallback(
      (result: GeneratedBatch) => dispatch({ t: 'generated', result }), []),
    toDocument,
  };
}

export type BatchForm = ReturnType<typeof useBatchForm>;
