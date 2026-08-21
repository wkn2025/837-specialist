/** Dev entry point: the bridge listens on :5000, which vite proxies /api to. */
import { createApp } from './api.ts';

const port = Number(process.env.PORT) || 5000;
createApp().listen(port, () => {
  console.log(`generator bridge on http://localhost:${port}`);
});
