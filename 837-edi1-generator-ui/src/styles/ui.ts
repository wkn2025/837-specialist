/** Style fragments shared by the sections, lifted from the handoff. */
import type { CSSProperties } from 'react';

export const mono = 'Arial, sans-serif';

export const card: CSSProperties = {
  background: '#fff',
  border: '1px solid #dde1ea',
  borderRadius: 8,
  overflow: 'hidden',
};

export const cardHeader: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '14px 20px',
  background: '#f7f8fa',
  borderBottom: '1px solid #eceef3',
};

export const autoTag: CSSProperties = {
  fontFamily: mono,
  fontSize: 10.5,
  letterSpacing: '.06em',
  textTransform: 'uppercase',
  background: '#eef4e0',
  color: '#6b7016',
  padding: '3px 8px',
  borderRadius: 4,
};

export const label: CSSProperties = {
  display: 'block',
  fontSize: 11.5,
  color: '#8892a6',
  marginBottom: 5,
  fontFamily: mono,
  letterSpacing: '.02em',
};

export const input: CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '9px 11px',
  border: '1px solid #dde1ea',
  borderRadius: 6,
  fontSize: 13.5,
  color: '#1a2233',
  fontFamily: mono,
  background: '#fff',
};

export const readOnlyInput: CSSProperties = {
  ...input,
  background: '#f2f4f7',
  color: '#5b6478',
  cursor: 'not-allowed',
};

export const sectionGap = 44;
