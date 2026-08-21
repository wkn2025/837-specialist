import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  // The Express bridge (server/api.ts) owns :5000 and shells out to
  // generate.py; the dev server never touches the generator directly.
  server: { port: 3000, proxy: { '/api': 'http://localhost:5000' } },
});
