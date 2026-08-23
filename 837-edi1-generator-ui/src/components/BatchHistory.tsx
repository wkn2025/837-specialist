/** The Batch History tab. */
import { downloadUrl } from '../api/client.js';
import { mono } from '../styles/ui.js';
import type { BatchRow } from '../api/types.js';

const COLUMNS = '70px 70px 70px 1fr 150px 110px 110px';

interface Props {
  rows: BatchRow[];
  loading: boolean;
  error: string | null;
}

function generatedOn(timestamp: string): string {
  if (!timestamp) return '—';
  const d = new Date(timestamp);
  return Number.isNaN(d.getTime()) ? timestamp : d.toLocaleString();
}

export function BatchHistory({ rows, loading, error }: Props) {
  return (
    <div style={{ maxWidth: 1040, margin: '0 auto', padding: '44px 24px 100px' }}>
      <h2 style={{ fontSize: 20, fontWeight: 600, margin: '0 0 6px' }}>
        Batch History
      </h2>
      <p style={{ fontSize: 13.5, color: '#5b6478', margin: '0 0 26px' }}>
        Previously generated 837 test files for this environment.
      </p>
      {error && (
        <p style={{ fontSize: 13, color: '#a1341f' }}>{error}</p>
      )}
      <div style={{
        border: '1px solid #dde1ea',
        borderRadius: 8,
        overflow: 'hidden',
        background: '#fff',
      }}
      >
        <div style={{
          display: 'grid',
          gridTemplateColumns: COLUMNS,
          background: '#f7f8fa',
          borderBottom: '1px solid #dde1ea',
          padding: '12px 20px',
          fontFamily: mono,
          fontSize: 11,
          color: '#8892a6',
          textTransform: 'uppercase',
          letterSpacing: '.06em',
        }}
        >
          <div>Batch</div>
          <div>Type</div>
          <div>Claims</div>
          <div>Output File</div>
          <div>Generated</div>
          <div>Status</div>
          <div />
        </div>
        {loading && rows.length === 0 && (
          <div style={{ padding: '18px 20px', fontSize: 13, color: '#5b6478' }}>
            Reading the masterfile…
          </div>
        )}
        {!loading && rows.length === 0 && !error && (
          <div style={{ padding: '18px 20px', fontSize: 13, color: '#5b6478' }}>
            No batches have been generated yet.
          </div>
        )}
        {rows.map((row) => (
          <div
            key={`${row.batchId}-${row.timestamp}-${row.isa13}`}
            style={{
              display: 'grid',
              gridTemplateColumns: COLUMNS,
              padding: '14px 20px',
              borderBottom: '1px solid #f2f3f6',
              alignItems: 'center',
              fontSize: 13,
            }}
          >
            <div style={{ fontWeight: 600, color: '#26408f' }}>
              {row.batchId.replace('Batch ', 'B')}
            </div>
            <div style={{ fontFamily: mono, color: '#5b6478' }}>
              {`837${row.type}`}
            </div>
            <div>{row.claims}</div>
            <div style={{
              fontFamily: mono,
              fontSize: 12,
              color: '#1a2233',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            >
              {row.file}
            </div>
            <div style={{ color: '#5b6478' }}>{generatedOn(row.timestamp)}</div>
            <div>
              <span style={{
                background: '#eef4e0',
                color: '#6b7016',
                fontFamily: mono,
                fontSize: 11,
                padding: '3px 9px',
                borderRadius: 4,
              }}
              >
                {row.status}
              </span>
            </div>
            <div>
              <a
                href={downloadUrl(row.batchId, 'x12')}
                style={{
                  display: 'inline-block',
                  padding: '6px 12px',
                  background: '#0084cc',
                  color: '#fff',
                  borderRadius: 5,
                  fontSize: 11.5,
                  fontWeight: 600,
                  fontFamily: mono,
                  textDecoration: 'none',
                }}
              >
                Download
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
