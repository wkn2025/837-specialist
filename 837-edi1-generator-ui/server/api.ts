/**
 * The bridge between the browser and the generator CLI.
 *
 * Every EDI decision stays in Python. This process shells out to
 * generate.py and forwards what it says; it never parses an .x12, never
 * computes an identifier, and never decides what a valid override is - the
 * generator's own refusals are the error messages the user sees.
 *
 * The override document travels as a temp FILE and every call goes through
 * execFile with an argument array, so nothing the browser sends reaches a
 * shell.
 */
import express from 'express';
import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { edi2Router, type Edi2Options } from './edi2.ts';

const run = promisify(execFile);

/** 837-edi1-generator-ui/server -> the repo root two levels up. */
export const REPO = path.resolve(import.meta.dirname, '..', '..');
const SKILL = path.join(REPO, 'skill', 'generating-uhcg-edi-files');
const GEN = path.join(SKILL, 'scripts', 'generate.py');

/**
 * claim_summary.py needs python-docx, so the repo venv is the interpreter
 * that can actually finish a run. PYTHON overrides it for other setups.
 */
function interpreter(): string {
  if (process.env.PYTHON) return process.env.PYTHON;
  const venv = process.platform === 'win32'
    ? path.join(REPO, '.venv', 'Scripts', 'python.exe')
    : path.join(REPO, '.venv', 'bin', 'python');
  return existsSync(venv) ? venv : 'python';
}

const MAX_CLAIMS = 200;      // the slider's ceiling in the handoff; the
                             // generator's own limit is 999

type TxType = 'I' | 'P';

function asType(type: unknown): TxType | null {
  return type === 'I' || type === 'P' ? type : null;
}

function badCount(claims: unknown): boolean {
  return !Number.isInteger(claims)
    || (claims as number) < 1 || (claims as number) > MAX_CLAIMS;
}

/** stderr is the generator's voice; surface it rather than a generic 500. */
function reason(e: unknown): string {
  const err = e as { stderr?: string; message?: string };
  return (err.stderr || err.message || 'the generator failed').trim();
}

async function python(args: string[], options: {
  maxBuffer?: number;
  timeout?: number;
} = {}): Promise<string> {
  const { stdout } = await run(interpreter(), args, {
    maxBuffer: options.maxBuffer ?? 32 * 1024 * 1024,
    timeout: options.timeout,
  });
  return stdout;
}

type Run = {
  type?: string;
  claims?: number;
  output?: string;
  timestamp?: string;
  overrides?: unknown;
};

async function masterfileRuns(): Promise<Run[]> {
  const raw = await fs.readFile(
    path.join(REPO, 'EDI1', 'masterfile.json'), 'utf8');
  return (JSON.parse(raw).runs ?? []) as Run[];
}

export function createApp(options: { edi2?: Edi2Options } = {}) {
  const app = express();
  app.use(express.json({ limit: '32mb' }));
  app.use('/api/edi2', edi2Router({
    ...options.edi2,
    runPython: options.edi2?.runPython ?? ((args) => python(args, {
      timeout: 30_000,
      maxBuffer: 64 * 1024 * 1024,
    })),
  }));

  // The seed's own values, as an override document the form can load.
  app.get('/api/defaults', async (req, res) => {
    const type = asType(req.query.type);
    if (!type) {
      return res.status(400).json({ error: 'type must be I or P' });
    }
    try {
      res.json(JSON.parse(
        await python([GEN, '--repo', REPO, '--type', type,
                      '--print-defaults'])));
    } catch (e) {
      res.status(400).json({ error: reason(e) });
    }
  });

  // The identifiers a run WOULD take. Peeking allocates nothing, so the
  // tiles can refresh on every slider move.
  app.get('/api/masterfile', async (req, res) => {
    const type = asType(req.query.type);
    const claims = Number(req.query.claims);
    if (!type) {
      return res.status(400).json({ error: 'type must be I or P' });
    }
    if (badCount(claims)) {
      return res.status(400).json({ error: `claims must be 1..${MAX_CLAIMS}` });
    }
    try {
      res.json(JSON.parse(
        await python([GEN, '--repo', REPO, '--type', type,
                      '--claims', String(claims), '--print-allocation'])));
    } catch (e) {
      res.status(400).json({ error: reason(e) });
    }
  });

  // Body: { type, claims, overrides }. The override document is a named key
  // rather than the rest of the body, because the document has a `claims`
  // array of its own and the batch size is also called `claims` - collapsing
  // the two into one object loses one of them.
  app.post('/api/generate', async (req, res) => {
    const { type: rawType, claims, overrides } = req.body ?? {};
    const type = asType(rawType);
    const doc = overrides ?? {};
    if (!type) {
      return res.status(400).json({ error: 'type must be I or P' });
    }
    if (badCount(claims)) {
      return res.status(400).json({ error: `claims must be 1..${MAX_CLAIMS}` });
    }
    const tmp = path.join(
      await fs.mkdtemp(path.join(os.tmpdir(), 'edi-ov-')), 'overrides.json');
    try {
      await fs.writeFile(tmp, JSON.stringify(doc));
      res.json(JSON.parse(
        await python([GEN, '--repo', REPO, '--type', type,
                      '--claims', String(claims), '--data', tmp, '--json'])));
    } catch (e) {
      res.status(400).json({ error: reason(e) });
    } finally {
      await fs.rm(path.dirname(tmp), { recursive: true, force: true })
        .catch(() => {});
    }
  });

  // Newest first. batchId indexes the masterfile's runs array, counting the
  // "imported" pseudo-run bootstrap writes - which is filtered out of the
  // listing but must not be renumbered away, or the download route would
  // fetch the wrong file.
  app.get('/api/history', async (_req, res) => {
    try {
      const runs = await masterfileRuns();
      res.json(runs
        .map((run, i) => ({ batchId: i + 1, ...run }))
        .filter((run) => run.type === 'I' || run.type === 'P')
        .reverse());
    } catch (e) {
      res.status(400).json({ error: reason(e) });
    }
  });

  app.get('/api/download/:batchId/:kind', async (req, res) => {
    const kind = req.params.kind;
    if (kind !== 'x12' && kind !== 'docx') {
      return res.status(400).json({ error: 'kind must be x12 or docx' });
    }
    const batchId = Number(req.params.batchId);
    try {
      const runs = await masterfileRuns();
      const run = Number.isInteger(batchId) ? runs[batchId - 1] : undefined;
      if (!run?.output) {
        return res.status(404).json({ error: `no batch ${req.params.batchId}` });
      }
      const x12 = path.resolve(REPO, run.output);
      const file = kind === 'x12'
        ? x12 : x12.replace(/\.x12$/, '_ClaimSummary.docx');
      // The manifest's output path is repo-relative and written by the
      // generator, but it reaches this line as user-influenced data. Confirm
      // it still lands inside the repo before streaming it.
      if (path.relative(REPO, file).startsWith('..')) {
        return res.status(400).json({ error: 'that batch is outside the repo' });
      }
      if (!existsSync(file)) {
        return res.status(404).json({ error: `${path.basename(file)} is gone` });
      }
      // dotfiles:'allow' - send() 404s any path with a dot-segment, and a
      // checkout can legitimately sit under one (a git worktree under
      // .claude/worktrees does). Containment was just checked above; this
      // switch decides nothing about which file is served.
      res.download(file, path.basename(file), { dotfiles: 'allow' });
    } catch (e) {
      res.status(400).json({ error: reason(e) });
    }
  });

  return app;
}
