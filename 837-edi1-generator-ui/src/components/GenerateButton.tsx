/**
 * Section 06: the generate-button state machine.
 *
 * gray "Complete Required Fields" -> blue "Generate File" -> green pill
 * "✓ File Generated", with a 300ms transition and an elastic pop on the flip.
 * Any edit reverts it, which the hook enforces by clearing `generated`.
 */
import { useEffect, useRef, useState } from 'react';
import { mono } from '../styles/ui.js';

interface Props {
  canGenerate: boolean;
  generated: boolean;
  busy: boolean;
  onGenerate: () => void;
}

export function GenerateButton(
  { canGenerate, generated, busy, onGenerate }: Props,
) {
  const [popping, setPopping] = useState(false);
  const wasGenerated = useRef(generated);

  useEffect(() => {
    if (generated && !wasGenerated.current) {
      setPopping(true);
      const t = setTimeout(() => setPopping(false), 500);
      return () => clearTimeout(t);
    }
    wasGenerated.current = generated;
    return undefined;
  }, [generated]);

  useEffect(() => { wasGenerated.current = generated; }, [generated]);

  const enabled = canGenerate && !busy;
  const label = busy
    ? 'Generating…'
    : generated
      ? '✓  File Generated'
      : canGenerate ? 'Generate File' : 'Complete Required Fields';

  return (
    <button
      type="button"
      disabled={!enabled && !generated}
      onClick={() => { if (enabled) onGenerate(); }}
      style={{
        padding: '13px 28px',
        borderRadius: generated ? 24 : 7,
        fontSize: 14.5,
        fontWeight: 600,
        cursor: enabled ? 'pointer' : 'not-allowed',
        border: 'none',
        background: generated ? '#5b8c1f' : (canGenerate ? '#0084cc' : '#c3c8d1'),
        color: '#fff',
        fontFamily: mono,
        opacity: canGenerate || generated ? 1 : 0.7,
        transform: popping ? 'scale(1.06)' : 'scale(1)',
        transition: 'background .3s, border-radius .3s, '
          + 'transform .5s cubic-bezier(.34,1.56,.64,1)',
      }}
    >
      {label}
    </button>
  );
}
