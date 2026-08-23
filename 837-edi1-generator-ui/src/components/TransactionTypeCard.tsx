/** Section 01: the two transaction-type cards. */
import { mono } from '../styles/ui.js';
import type { TxType } from '../api/types.js';

export interface TypeInfo {
  id: TxType;
  code: string;
  name: string;
  desc: string;
  seed: string;
}

/** Seeds named here are the ones seeds.py actually registers. */
export const TYPES: TypeInfo[] = [
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

interface Props {
  info: TypeInfo;
  selected: boolean;
  onSelect: (id: TxType) => void;
}

export function TransactionTypeCard({ info, selected, onSelect }: Props) {
  return (
    <div
      role="radio"
      aria-checked={selected}
      tabIndex={0}
      onClick={() => onSelect(info.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(info.id);
        }
      }}
      style={{
        flex: 1,
        minWidth: 280,
        padding: '22px 24px',
        borderRadius: 8,
        cursor: 'pointer',
        border: `1.5px solid ${selected ? '#26408f' : '#dde1ea'}`,
        background: selected ? '#eef1f9' : '#fff',
      }}
    >
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 14,
      }}
      >
        <div style={{
          fontFamily: mono,
          fontWeight: 700,
          fontSize: 13,
          color: selected ? '#fff' : '#26408f',
          background: selected ? '#26408f' : '#eef1f9',
          padding: '5px 10px',
          borderRadius: 5,
        }}
        >
          {info.code}
        </div>
        <div style={{
          width: 20,
          height: 20,
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 12,
          background: selected ? '#c7cd3d' : 'transparent',
          color: '#26408f',
          border: `1.5px solid ${selected ? '#c7cd3d' : '#dde1ea'}`,
        }}
        >
          ✓
        </div>
      </div>
      <div style={{ fontSize: 17, fontWeight: 600, marginBottom: 6 }}>
        {info.name}
      </div>
      <div style={{ fontSize: 13.5, color: '#5b6478', lineHeight: 1.5 }}>
        {info.desc}
      </div>
      <div style={{
        marginTop: 16,
        fontFamily: mono,
        fontSize: 11,
        color: '#8892a6',
        borderTop: '1px solid #eceef3',
        paddingTop: 12,
      }}
      >
        {`Seed: ${info.seed}`}
      </div>
    </div>
  );
}
