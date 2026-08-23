/**
 * The New Batch form's state.
 *
 * Every value starts as the generator's own default (GET /api/defaults, which
 * is `generate.py --print-defaults`), never as a hand-written constant: the
 * handoff's sample data does not match the registered seeds, and a form that
 * disagreed with the seed would offer edits the generator then refuses.
 *
 * Two rules the generator owns and this hook only obeys:
 *   - 837I savings is derived (15% of the charge), so toDocument() omits it.
 *   - Service dates come from the allocator's window, so they are read-only.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  ClaimDoc, FormState, GenerateResult, Identity, IdentityGroup, Line,
  OverrideDocument, TxType,
} from '../api/types.js';

export interface UseBatchFormOptions {
  initialType?: TxType;
  initialClaims?: number;
}

const blank: Identity = {
  subscriber: { last: '', first: '', memberId: '', dob: '' },
  billingProvider: { name: '', npi: '' },
};

async function fetchDefaults(type: TxType, claims: number)
: Promise<OverrideDocument> {
  const res = await fetch(`/api/defaults?type=${type}&claims=${claims}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { error?: string }).error ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as OverrideDocument;
}

/** A defaults claim, with savings filled in so the 837P column has a value. */
function toClaimDoc(claim: OverrideDocument['claims'][number]): ClaimDoc {
  return {
    n: claim.n,
    principalDiagnosis: claim.principalDiagnosis ?? '',
    lines: claim.lines.map((l) => ({
      date: l.date,
      billed: l.billed,
      savings: l.savings ?? '',
    })),
  };
}

function filled(...values: Array<string | undefined>): boolean {
  return values.every((v) => typeof v === 'string' && v.trim() !== '');
}

export function useBatchForm(options: UseBatchFormOptions = {}) {
  const [form, setForm] = useState<FormState>(() => ({
    type: options.initialType ?? 'I',
    claims: options.initialClaims ?? 3,
    identity: blank,
    claimDocs: [],
    expanded: new Set<number>(),
    generated: false,
  }));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [editedGroups, setEditedGroups] = useState<Set<string>>(new Set());
  // A slow response for a type the user has already switched away from must
  // not overwrite the newer one.
  const request = useRef(0);

  const loadFor = useCallback((type: TxType, claims: number) => {
    const ticket = ++request.current;
    setLoading(true);
    setError(null);
    fetchDefaults(type, claims).then((doc) => {
      if (ticket !== request.current) return;
      setForm((f) => ({
        ...f,
        type,
        claims,
        identity: doc.identity,
        claimDocs: doc.claims.map(toClaimDoc),
        expanded: new Set<number>(),
        generated: false,
      }));
      setEditedGroups(new Set());
      setResult(null);
      setLoading(false);
    }).catch((e: unknown) => {
      if (ticket !== request.current) return;
      setError(e instanceof Error ? e.message : String(e));
      setLoading(false);
    });
  }, []);

  // The initial load, and every change of transaction type.
  useEffect(() => {
    loadFor(form.type, form.claims);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.type]);

  /** Any content edit invalidates a generated file. */
  const edit = useCallback((fn: (f: FormState) => FormState) => {
    setForm((f) => ({ ...fn(f), generated: false }));
    setResult(null);
  }, []);

  const markEdited = useCallback((group: string) => {
    setEditedGroups((g) => (g.has(group) ? g : new Set(g).add(group)));
  }, []);

  const setType = useCallback((type: TxType) => {
    setForm((f) => (f.type === type ? f : { ...f, type, generated: false }));
  }, []);

  const setClaims = useCallback((claims: number) => {
    setForm((f) => {
      if (claims === f.claims) return f;
      if (claims <= f.claimDocs.length) {
        // Trimming needs no round trip, and keeps the edits that survive.
        return {
          ...f,
          claims,
          claimDocs: f.claimDocs.slice(0, claims),
          generated: false,
        };
      }
      return { ...f, claims, generated: false };
    });
    setResult(null);
  }, []);

  // Growing the batch needs the claims the seed would supply for the new
  // slots; the generator cycles its seed blocks, so only it knows them.
  useEffect(() => {
    if (loading || error) return;
    if (form.claimDocs.length >= form.claims) return;
    const ticket = ++request.current;
    let cancelled = false;
    fetchDefaults(form.type, form.claims).then((doc) => {
      if (cancelled || ticket !== request.current) return;
      setForm((f) => {
        if (f.claimDocs.length >= f.claims) return f;
        const grown = doc.claims.slice(f.claimDocs.length).map(toClaimDoc);
        return { ...f, claimDocs: [...f.claimDocs, ...grown] };
      });
    }).catch((e: unknown) => {
      if (cancelled) return;
      setError(e instanceof Error ? e.message : String(e));
    });
    return () => { cancelled = true; };
  }, [form.claims, form.claimDocs.length, form.type, loading, error]);

  const updateIdentity = useCallback(
    (group: IdentityGroup, field: string, value: string) => {
      markEdited(group);
      edit((f) => {
        if (group === 'taxId') return { ...f, identity: { ...f.identity, taxId: value } };
        const current = f.identity[group];
        if (!current) return f;
        return {
          ...f,
          identity: { ...f.identity, [group]: { ...current, [field]: value } },
        };
      });
    }, [edit, markEdited]);

  const updateDiagnosis = useCallback((n: number, value: string) => {
    markEdited(`diagnosis:${n}`);
    edit((f) => ({
      ...f,
      claimDocs: f.claimDocs.map((c) =>
        (c.n === n ? { ...c, principalDiagnosis: value } : c)),
    }));
  }, [edit, markEdited]);

  const updateLine = useCallback(
    (n: number, index: number, field: keyof Line, value: string) => {
      edit((f) => ({
        ...f,
        claimDocs: f.claimDocs.map((c) => (c.n === n
          ? {
            ...c,
            lines: c.lines.map((l, i) =>
              (i === index ? { ...l, [field]: value } : l)),
          }
          : c)),
      }));
    }, [edit]);

  const addLine = useCallback((n: number) => {
    edit((f) => ({
      ...f,
      claimDocs: f.claimDocs.map((c) => {
        if (c.n !== n) return c;
        // A new line copies the last one's date: the generator splices a
        // seed loop, and a date outside that loop's window is refused.
        const last = c.lines[c.lines.length - 1];
        return { ...c, lines: [...c.lines, { ...last }] };
      }),
    }));
  }, [edit]);

  const removeLine = useCallback((n: number, index: number) => {
    edit((f) => ({
      ...f,
      claimDocs: f.claimDocs.map((c) => ((c.n === n && c.lines.length > 1)
        ? { ...c, lines: c.lines.filter((_, i) => i !== index) }
        : c)),
    }));
  }, [edit]);

  const toggleExpanded = useCallback((n: number) => {
    // Presentation only: expanding a claim changes no claim content, so a
    // generated file stays generated.
    setForm((f) => {
      const expanded = new Set(f.expanded);
      if (!expanded.delete(n)) expanded.add(n);
      return { ...f, expanded };
    });
  }, []);

  const markGenerated = useCallback((generated: GenerateResult) => {
    setResult(generated);
    setForm((f) => ({ ...f, generated: true }));
  }, []);

  const canGenerate = useMemo(() => {
    if (loading || error) return false;
    const { identity, claimDocs, claims } = form;
    if (claimDocs.length !== claims || claims < 1) return false;
    const { subscriber: s, billingProvider: b, attendingProvider: a } = identity;
    if (!filled(s.last, s.first, s.memberId, s.dob)) return false;
    if (!filled(b.name, b.npi)) return false;
    if (a && !filled(a.last, a.first, a.npi)) return false;
    if (identity.taxId !== undefined && !filled(identity.taxId)) return false;
    return claimDocs.every((c) =>
      filled(c.principalDiagnosis)
      && c.lines.length > 0
      && c.lines.every((l) => filled(l.date, l.billed)
        && Number(l.billed) > 0
        && (form.type === 'I' || filled(l.savings))));
  }, [form, loading, error]);

  /** The override document, exactly as POST /api/generate wants it. */
  const toDocument = useCallback((): OverrideDocument => ({
    identity: form.identity,
    claims: form.claimDocs.map((c) => ({
      n: c.n,
      principalDiagnosis: c.principalDiagnosis,
      lines: c.lines.map((l) => (form.type === 'I'
        // 837I savings is an exact 85/15 split the generator computes; a
        // value sent from here would be refused as contradictory.
        ? { date: l.date, billed: l.billed }
        : { date: l.date, billed: l.billed, savings: l.savings })),
    })),
  }), [form]);

  return {
    form,
    loading,
    error,
    result,
    canGenerate,
    editedGroups,
    setType,
    setClaims,
    updateIdentity,
    updateDiagnosis,
    updateLine,
    addLine,
    removeLine,
    toggleExpanded,
    markGenerated,
    toDocument,
    reload: () => loadFor(form.type, form.claims),
  };
}
