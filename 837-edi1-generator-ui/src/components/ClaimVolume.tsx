/** Section 02: the claim-volume slider. */
import { mono } from '../styles/ui.js';

interface Props {
  claims: number;
  max: number;
  onChange: (claims: number) => void;
}

export function ClaimVolume({ claims, max, onChange }: Props) {
  return (
    <div style={{
      background: '#fff',
      border: '1px solid #dde1ea',
      borderRadius: 8,
      padding: '24px 26px',
    }}
    >
      <div style={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        marginBottom: 14,
      }}
      >
        <label htmlFor="claim-volume" style={{ fontSize: 13.5, color: '#5b6478' }}>
          Claims in this batch
        </label>
        <span style={{
          fontFamily: mono, fontSize: 26, fontWeight: 600, color: '#26408f',
        }}
        >
          {claims}
        </span>
      </div>
      <input
        id="claim-volume"
        type="range"
        min={1}
        max={max}
        value={claims}
        onChange={(e) => onChange(Number(e.target.value) || 1)}
        style={{ width: '100%', height: 6 }}
      />
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        fontFamily: mono,
        fontSize: 11,
        color: '#8892a6',
        marginTop: 6,
      }}
      >
        <span>1</span>
        <span>{`${max} max`}</span>
      </div>
    </div>
  );
}
