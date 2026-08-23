/**
 * A numbered section heading, with the handoff's one-time reveal.
 *
 * The prototype used GSAP ScrollTrigger; an IntersectionObserver at the same
 * 88% threshold does the same job without pulling in a library, which the
 * handoff explicitly allows.
 */
import { useEffect, useRef, useState } from 'react';
import { mono } from '../styles/ui.js';

interface Props {
  number: string;
  title: string;
  note?: string;
}

export function SectionHeading({ number, title, note }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setShown(true);
      return;
    }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setShown(true);
        io.disconnect();
      }
    }, { rootMargin: '0px 0px -12% 0px' });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: 12,
        marginBottom: 16,
        opacity: shown ? 1 : 0,
        transform: shown ? 'translateY(0)' : 'translateY(18px)',
        transition: 'opacity .6s ease-out, transform .6s ease-out',
      }}
    >
      <div style={{
        fontFamily: mono,
        fontSize: 12,
        color: '#c7cd3d',
        fontWeight: 700,
        background: '#26408f',
        padding: '2px 8px',
        borderRadius: 4,
      }}
      >
        {number}
      </div>
      <h2 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>{title}</h2>
      {note && <span style={{ fontSize: 12.5, color: '#8892a6' }}>{note}</span>}
    </div>
  );
}
