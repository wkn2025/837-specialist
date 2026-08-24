/**
 * The bridge between the browser and skill/generating-uhcg-edi-files.
 *
 * Every rule about what a valid 837 override is lives in the Python
 * generator; this file owns none of them. It shells out with execFile and an
 * argument array (never a shell string), hands the override document over as
 * a temp file rather than an argument, and passes the generator's own error
 * text back to the caller unedited.
 */
import express from 'express';
import type { Request, Response } from 'express';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { edi2Router, type Edi2Options } from './edi2.ts';

const run = promisify(execFile);

const GEN_REL = 'skill/generating-uhcg-edi-files/scripts/generate.py';
const MAX_CLAIMS = 200;
const BATCH_ID = /^Batch \d+$/;
const DOWNLOAD_KINDS = new Set(['x12', 'docx', 'manifest']);

export interface Options {
  /**
   * The EDI2 Validator's read-only upload bridge (main). It is a router of
   * its own with its own Python entry point, so it is configured here
   * rather than folded into the generator's options.
   */
  edi2?: Edi2Options;
  /** Data root: the tree holding EDI1/. Mirrors the CLI's --repo. */
  repo?: string;
  python?: string;
  /** Where generate.py lives. Defaults to this checkout, not to `repo`. */
  generator?: string;
}

/** Walk up from here until the directory holding the generator turns up. */
export function findRepo(start?: string): string {
  let dir = start ?? path.dirname(fileURLToPath(import.meta.url));
  for (;;) {
    if (fs.existsSync(path.join(dir, GEN_REL))) return dir;
    const up = path.dirname(dir);
    if (up === dir) throw new Error(`no repo containing ${GEN_REL} above ${dir}`);
    dir = up;
  }
}

function errorText(e: unknown): string {
  const err = e as { stderr?: string | Buffer; message?: string };
  const stderr = err.stderr ? String(err.stderr).trim() : '';
  return stderr || String(err.message ?? e).trim();
}

/** A batch's directory name, from the repo-relative path of its .x12. */
function batchIdOf(rel: string): string {
  return path.basename(path.dirname(rel));
}

export function createApp(opts: Options = {}) {
  const repo = opts.repo ?? findRepo();
  const python = opts.python ?? process.env.PYTHON ?? 'python';
  // The generator is code and lives in this checkout; `repo` is only the data
  // root it reads and writes, exactly as the CLI's --repo means.
  const gen = opts.generator ?? path.join(findRepo(), GEN_REL);
  const app = express();

  const py = (args: string[]) =>
    run(python, [gen, '--repo', repo, ...args], { maxBuffer: 32 * 1024 * 1024 });

  // Mounted before express.json: /api/edi2/validate takes raw bytes, and a
  // JSON body parser ahead of it would consume - and fail on - the upload.
  app.use('/api/edi2', edi2Router({
    ...opts.edi2,
    runPython: opts.edi2?.runPython ?? (async (args: string[]) => {
      const { stdout } = await run(python, args, {
        maxBuffer: 64 * 1024 * 1024, timeout: 30_000,
      });
      return stdout;
    }),
  }));

  app.use(express.json({ limit: '4mb' }));

  const readType = (value: unknown): 'I' | 'P' | null =>
    value === 'I' || value === 'P' ? value : null;

  /** The seed's own values, shaped as an override document the UI can edit. */
  app.get('/api/defaults', async (req: Request, res: Response) => {
    const type = readType(req.query.type);
    if (!type) return res.status(400).json({ error: 'type must be I or P' });
    const args = ['--type', type, '--print-defaults'];
    if (req.query.claims !== undefined) {
      const claims = Number(req.query.claims);
      if (!Number.isInteger(claims) || claims < 1 || claims > MAX_CLAIMS) {
        return res.status(400).json({ error: 'claims must be 1..200' });
      }
      args.push('--claims', String(claims));
    }
    try {
      const { stdout } = await py(args);
      return res.json(JSON.parse(stdout));
    } catch (e) {
      return res.status(400).json({ error: errorText(e) });
    }
  });

  /** The identifiers the next batch would take - previewed, not consumed. */
  app.get('/api/masterfile', async (req: Request, res: Response) => {
    const type = readType(req.query.type);
    if (!type) return res.status(400).json({ error: 'type must be I or P' });
    const claims = Number(req.query.claims ?? 1);
    if (!Number.isInteger(claims) || claims < 1 || claims > MAX_CLAIMS) {
      return res.status(400).json({ error: 'claims must be 1..200' });
    }
    try {
      const { stdout } = await py(['--type', type, '--claims', String(claims),
        '--print-allocation']);
      return res.json(JSON.parse(stdout));
    } catch (e) {
      return res.status(400).json({ error: errorText(e) });
    }
  });

  /** Batches already generated, newest first, straight from the masterfile. */
  app.get('/api/history', async (_req: Request, res: Response) => {
    try {
      const raw = await fsp.readFile(
        path.join(repo, 'EDI1', 'masterfile.json'), 'utf8');
      const runs: Array<Record<string, unknown>> =
        JSON.parse(raw).runs ?? [];
      const rows = runs
        // the bootstrap run records what was on disk, not a generated batch
        .filter((r) => typeof r.output === 'string' && r.type !== 'imported')
        .map((r) => {
          const output = r.output as string;
          const clm01 = (r.clm01 as string[]) ?? [];
          return {
            batchId: batchIdOf(output),
            type: r.type as string,
            claims: r.claims as number,
            output,
            file: path.basename(output),
            timestamp: (r.timestamp as string) ?? '',
            isa13: r.isa13 as string,
            gs06: r.gs06 as string,
            statement: r.statement as string,
            clm01: clm01.length ? [clm01[0], clm01[clm01.length - 1]] : [],
            status: 'Validated',
          };
        })
        .reverse();
      return res.json(rows);
    } catch (e) {
      return res.status(500).json({ error: errorText(e) });
    }
  });

  /**
   * Generate a batch. The body is { type, claims, document } - `document` is
   * the override document verbatim, kept in its own key so its `claims` array
   * cannot collide with the batch's claim count.
   */
  app.post('/api/generate', async (req: Request, res: Response) => {
    const { type, claims, document } = req.body ?? {};
    if (type !== 'I' && type !== 'P') {
      return res.status(400).json({ error: 'type must be I or P' });
    }
    if (!Number.isInteger(claims) || claims < 1 || claims > MAX_CLAIMS) {
      return res.status(400).json({ error: 'claims must be 1..200' });
    }
    if (document !== undefined
        && (document === null || typeof document !== 'object'
            || Array.isArray(document))) {
      return res.status(400).json({ error: 'document must be an object' });
    }
    const tmp = path.join(os.tmpdir(), `ov-${Date.now()}-${process.pid}.json`);
    await fsp.writeFile(tmp, JSON.stringify(document ?? {}), 'utf8');
    try {
      const { stdout } = await py(['--type', type, '--claims', String(claims),
        '--data', tmp, '--json']);
      return res.json(JSON.parse(stdout));
    } catch (e) {
      return res.status(400).json({ error: errorText(e) });
    } finally {
      await fsp.unlink(tmp).catch(() => {});
    }
  });

  /** Stream one artefact of a generated batch back to the browser. */
  app.get('/api/download/:batchId/:kind', (req: Request, res: Response) => {
    const batchId = String(req.params.batchId);
    const kind = String(req.params.kind);
    if (!BATCH_ID.test(batchId)) {
      return res.status(400).json({ error: 'batchId must be "Batch <n>"' });
    }
    if (!DOWNLOAD_KINDS.has(kind)) {
      return res.status(400).json({ error: 'kind must be x12, docx or manifest' });
    }
    const dir = path.join(repo, 'EDI1', batchId);
    let names: string[];
    try {
      names = fs.readdirSync(dir);
    } catch {
      return res.status(404).json({ error: `${batchId} has not been generated` });
    }
    const suffix = kind === 'x12' ? '.x12'
      : kind === 'docx' ? '.docx' : '.manifest.json';
    const name = names.find((n) => n.endsWith(suffix)
      && !(kind === 'x12' && n.endsWith('.manifest.json')));
    if (!name) {
      return res.status(404).json({ error: `${batchId} has no ${kind}` });
    }
    return res.download(path.join(dir, name), name);
  });

  return app;
}

const invokedDirectly = process.argv[1]
  && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));

if (invokedDirectly) {
  const port = Number(process.env.PORT ?? 5000);
  createApp().listen(port, () => {
    process.stdout.write(`generator bridge listening on :${port}\n`);
  });
}
