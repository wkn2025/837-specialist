import React from 'react';
import { createRoot } from 'react-dom/client';
import './styles/tokens.css';

const root = document.getElementById('root');
if (!root) throw new Error('#root is missing from index.html');

createRoot(root).render(
  <React.StrictMode>
    <div style={{ maxWidth: 900, margin: '0 auto', padding: 24 }}>
      837 EDI Test File Generator
    </div>
  </React.StrictMode>,
);
