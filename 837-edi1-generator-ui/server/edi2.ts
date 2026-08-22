/** Secure, read-only raw upload bridge to the deterministic EDI2 validator. */
import express, { Router } from 'express';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';


export const DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const VALIDATE_API = path.resolve(
  import.meta.dirname, '..', '..', 'skill', 'assessing-edi2-files',
  'validate_api.py');

export type Edi2Options = {
  maxUploadBytes?: number;
  runPython?: (args: string[]) => Promise<string>;
  tempRoot?: string;
  validateApi?: string;
  removeDirectory?: (directory: string) => Promise<void>;
  reportOperationalError?: (message: string) => void;
};

function configuredLimit(options: Edi2Options): number {
  if (options.maxUploadBytes !== undefined) return options.maxUploadBytes;
  const configured = Number(process.env.EDI2_MAX_UPLOAD_BYTES);
  return Number.isFinite(configured) && configured > 0
    ? configured : DEFAULT_MAX_UPLOAD_BYTES;
}

function safeFilename(value: string | undefined): string {
  const normalized = String(value || 'upload.x12').replaceAll('\\', '/');
  const basename = path.posix.basename(normalized)
    .replace(/[\u0000-\u001f\u007f]/g, '')
    .slice(0, 255);
  return basename || 'upload.x12';
}

function operationalReason(error: unknown): string {
  const stdout = (error as { stdout?: string }).stdout;
  if (stdout) {
    try {
      const parsed = JSON.parse(stdout) as { error?: string };
      if (parsed.error) return parsed.error;
    } catch {
      // The response remains generic when the subprocess did not emit JSON.
    }
  }
  return 'EDI2 validation could not be completed';
}

export function edi2Router(options: Edi2Options = {}) {
  const router = Router();
  const limit = configuredLimit(options);
  const runPython = options.runPython ?? (async () => {
    throw new Error('EDI2 Python runner is not configured');
  });
  const removeDirectory = options.removeDirectory ?? ((directory) => fs.rm(
    directory, { recursive: true, force: true }));
  const reportOperationalError = options.reportOperationalError
    ?? ((message: string) => console.error(message));
  const raw = express.raw({
    type: 'application/octet-stream', limit, inflate: false,
  });

  router.post('/validate', (req, res, next) => {
    if (!req.is('application/octet-stream')) {
      return res.status(415).json({
        error: 'content-type must be application/octet-stream',
      });
    }
    return raw(req, res, next);
  }, async (req, res) => {
    const body = Buffer.isBuffer(req.body) ? req.body : Buffer.alloc(0);
    if (!body.length) {
      return res.status(400).json({ error: 'EDI2 file is empty' });
    }
    if (body.includes(0)) {
      return res.status(400).json({ error: 'EDI2 file contains NUL bytes' });
    }

    const filename = safeFilename(req.get('x-edi-filename'));
    let directory: string | undefined;
    let payload: unknown;
    let failure: unknown;
    try {
      directory = await fs.mkdtemp(path.join(
        options.tempRoot ?? os.tmpdir(), 'edi2-'));
      const input = path.join(directory, 'upload.x12');
      await fs.writeFile(input, body, { mode: 0o600 });
      const stdout = await runPython([
        options.validateApi ?? VALIDATE_API,
        '--file', input,
        '--filename', filename,
      ]);
      payload = JSON.parse(stdout);
    } catch (error) {
      failure = error;
    } finally {
      if (directory) {
        let cleanupFailure: unknown;
        for (let attempt = 0; attempt < 2; attempt += 1) {
          try {
            await removeDirectory(directory);
            cleanupFailure = undefined;
            break;
          } catch (error) {
            cleanupFailure = error;
          }
        }
        if (cleanupFailure) {
          reportOperationalError('EDI2 temporary upload cleanup failed');
        }
        failure ??= cleanupFailure;
      }
    }
    if (failure) {
      return res.status(500).json({ error: operationalReason(failure) });
    }
    return res.json(payload);
  });

  router.use((error: unknown, _req: express.Request,
              res: express.Response, next: express.NextFunction) => {
    const typed = error as { type?: string };
    if (typed.type === 'entity.too.large') {
      return res.status(413).json({
        error: `EDI2 file exceeds the ${limit}-byte upload limit`,
      });
    }
    if (typed.type === 'encoding.unsupported') {
      return res.status(415).json({
        error: 'compressed EDI2 request bodies are not accepted',
      });
    }
    if (typed.type) {
      return res.status(400).json({ error: 'EDI2 upload could not be read' });
    }
    return next(error);
  });

  return router;
}
