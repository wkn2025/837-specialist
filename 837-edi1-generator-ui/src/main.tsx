import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.js';
import './styles/tokens.css';

const root = document.getElementById('root');
if (!root) throw new Error('#root is missing from index.html');

createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
