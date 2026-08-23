/**
 * Section 03: the four read-only identifier tiles.
 *
 * Values come from the allocator's own preview, so what the tiles show is
 * what the file will carry - never a number derived in the browser.
 */
import { mono } from '../styles/ui.js';
import type { AllocationPreview } from '../api/types.js';

interface Props {
  preview: AllocationPreview | null;
  error: string | null;
}

function range(values: string[]): string {
  if (values.length === 0) return '—';
  return values.length === 1
    ? values[0]
    : `${values[0]}–${values[values.length - 1]}`;
}

export function IdentifierTiles({ preview, error }: Props) {
  const tiles = [
    { label: 'Next Batch', value: preview?.batchId },
    { label: 'ISA13', value: preview?.isa13 },
    { label: 'GS06', value: preview?.gs06 },
    { label: 'BHT03 Range', value: preview ? range(preview.bht03) : undefined },
  ];

  return (
    <div>
      <div style={{ display: 'flex', gap: 14 }}>
        {tiles.map((t) => (
          <div
            key={t.label}
            style={{
              flex: 1,
              border: '1px solid #dde1ea',
              borderRadius: 8,
              padding: '14px 16px',
              background: '#f7f8fa',
            }}
          >
            <div style={{
              fontSize: 10.5,
              color: '#8892a6',
              textTransform: 'uppercase',
              letterSpacing: '.08em',
              fontFamily: mono,
              marginBottom: 6,
            }}
            >
              {t.label}
            </div>
            <div style={{
              fontSize: 14.5, fontWeight: 600, color: '#26408f', fontFamily: mono,
            }}
            >
              {t.value ?? '…'}
            </div>
          </div>
        ))}
      </div>
      {error && (
        <div style={{ marginTop: 10, fontSize: 12.5, color: '#a1341f' }}>
          {`Could not read the masterfile: ${error}`}
        </div>
      )}
    </div>
  );
}
