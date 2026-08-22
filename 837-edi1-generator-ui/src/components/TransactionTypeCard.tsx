/**
 * Section 01. The two cards name the seed each type is built from, because
 * that seed is what every unedited byte of the output will be.
 */
import type { TxType } from '@/api/types';

const TYPES: Array<{
  id: TxType; code: string; name: string; desc: string; seed: string;
}> = [
  {
    id: 'P',
    code: '837P',
    name: 'Professional',
    desc: 'Physician, non-institutional, and outpatient practitioner services '
      + 'billed by CPT/HCPCS procedure code.',
    seed: 'EDI1/Sample 837P/ERCT_UHCG_P_...x12',
  },
  {
    id: 'I',
    code: '837I',
    name: 'Institutional',
    desc: 'Hospital and facility services billed by revenue code and type of '
      + 'bill.',
    seed: 'EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12',
  },
];

export function TransactionTypeCards({ value, onChange }: {
  value: TxType;
  onChange: (t: TxType) => void;
}) {
  return (
    <div className="type-grid">
      {TYPES.map((t) => (
        <button
          key={t.id}
          type="button"
          className="type-card"
          aria-pressed={value === t.id}
          onClick={() => onChange(t.id)}
        >
          <div className="type-card__top">
            <div className="type-badge">{t.code}</div>
            <div className="type-check" aria-hidden="true">
              {value === t.id ? '✓' : ''}
            </div>
          </div>
          <div className="type-name">{t.name}</div>
          <div className="type-desc">{t.desc}</div>
          <div className="type-seed">Seed: {t.seed}</div>
        </button>
      ))}
    </div>
  );
}
