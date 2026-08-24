// @vitest-environment node
/**
 * Task 10: the bridge is the only thing between the browser and a CLI that
 * allocates never-reused identifiers. Every test that could allocate runs
 * against a throwaway copy of EDI1/, the same way the Python CLI tests do.
 */
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import request from 'supertest';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { gzipSync } from 'node:zlib';
import { createApp, findRepo } from './api.js';

const REPO = findRepo();
const app = createApp({ repo: REPO });

/** A copy of EDI1/ so allocation cannot disturb the real masterfile. */
function tempRepo(): string {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'edi-api-'));
  fs.cpSync(path.join(REPO, 'EDI1'), path.join(tmp, 'EDI1'), {
    recursive: true,
  });
  return tmp;
}

describe('GET /api/defaults', () => {
  it('returns the seed as an override document', async () => {
    const res = await request(app).get('/api/defaults?type=I');
    expect(res.status).toBe(200);
    expect(res.body.identity.subscriber.memberId).toBeTruthy();
    expect(Array.isArray(res.body.claims)).toBe(true);
  });

  it('fits the document to the requested claim count', async () => {
    const res = await request(app).get('/api/defaults?type=I&claims=3');
    expect(res.status).toBe(200);
    expect(res.body.claims.map((c: { n: number }) => c.n)).toEqual([1, 2, 3]);
  });

  it('rejects a transaction type it does not know', async () => {
    const res = await request(app).get('/api/defaults?type=Z');
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/type/i);
  });
});

describe('GET /api/masterfile', () => {
  it('previews the identifiers the next batch would take', async () => {
    const before = fs.readFileSync(path.join(REPO, 'EDI1/masterfile.json'));
    const res = await request(app).get('/api/masterfile?type=I&claims=2');
    expect(res.status).toBe(200);
    expect(res.body.isa13).toMatch(/^\d{9}$/);
    expect(res.body.clm01).toHaveLength(2);
    expect(res.body.batchId).toMatch(/^Batch \d+$/);
    // read-only: previewing must not consume an identifier
    expect(fs.readFileSync(path.join(REPO, 'EDI1/masterfile.json')))
      .toEqual(before);
  });
});

describe('GET /api/history', () => {
  it('lists generated batches, newest first', async () => {
    const res = await request(app).get('/api/history');
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    expect(res.body.length).toBeGreaterThan(0);
    const ts = res.body.map((b: { timestamp: string }) => b.timestamp);
    expect([...ts].sort().reverse()).toEqual(ts);
    for (const row of res.body) {
      expect(row.batchId).toMatch(/^Batch \d+$/);
      expect(['I', 'P']).toContain(row.type);
    }
  });
});

describe('POST /api/generate', () => {
  it('rejects a claim count outside 1..200', async () => {
    const res = await request(app).post('/api/generate')
      .send({ type: 'I', claims: 201, document: {} });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/1\.\.200/);
  });

  it('rejects a transaction type that is not I or P', async () => {
    const res = await request(app).post('/api/generate')
      .send({ type: 'X', claims: 1, document: {} });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/must be I or P/);
  });

  it("surfaces the generator's own error message", async () => {
    const res = await request(app).post('/api/generate')
      .send({ type: 'I', claims: 1, document: { claims: [{ n: 99 }] } });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/outside the batch/);
  });

  it('leaves the real masterfile alone when the document is refused',
    async () => {
      const before = fs.readFileSync(path.join(REPO, 'EDI1/masterfile.json'));
      await request(app).post('/api/generate')
        .send({ type: 'I', claims: 1, document: { claims: [{ n: 99 }] } });
      expect(fs.readFileSync(path.join(REPO, 'EDI1/masterfile.json')))
        .toEqual(before);
    });
});

describe('a real generated batch', () => {
  let tmp: string;
  let scoped: ReturnType<typeof createApp>;
  let body: {
    batchId: string; x12: string; manifest: string; docx: string | null;
  };

  beforeAll(async () => {
    tmp = tempRepo();
    scoped = createApp({ repo: tmp });
    const res = await request(scoped).post('/api/generate').send({
      type: 'I',
      claims: 2,
      document: { identity: { subscriber: { last: 'DOE' } } },
    });
    expect(res.status, JSON.stringify(res.body)).toBe(200);
    body = res.body;
  }, 120_000);

  afterAll(() => fs.rmSync(tmp, { recursive: true, force: true }));

  it('writes the x12 and its manifest', () => {
    expect(fs.existsSync(path.join(tmp, body.x12))).toBe(true);
    expect(fs.existsSync(path.join(tmp, body.manifest))).toBe(true);
  });

  it('carries the edit that was submitted', () => {
    expect(fs.readFileSync(path.join(tmp, body.x12), 'ascii'))
      .toContain('NM1*IL*1*DOE*');
  });

  it('records the declaration in the manifest', () => {
    const man = JSON.parse(fs.readFileSync(path.join(tmp, body.manifest),
      'utf8'));
    expect(man.overrides).toEqual({
      identity: { subscriber: { last: 'DOE' } },
    });
  });

  it('serves the batch back for download', async () => {
    const res = await request(scoped)
      .get(`/api/download/${encodeURIComponent(body.batchId)}/x12`);
    expect(res.status).toBe(200);
    // an .x12 is served as a download, so supertest hands back the bytes
    expect(Buffer.from(res.body).toString('ascii')).toContain('ISA*');
    expect(res.headers['content-disposition']).toMatch(/attachment/);
  });

  it('appears at the top of the history', async () => {
    const res = await request(scoped).get('/api/history');
    expect(res.body[0].batchId).toBe(body.batchId);
  });
});

describe('GET /api/download', () => {
  it('refuses a batch id that is not a batch id', async () => {
    const res = await request(app).get('/api/download/..%2F..%2Fetc/x12');
    expect(res.status).toBe(400);
  });

  it('refuses a kind it does not serve', async () => {
    const res = await request(app).get('/api/download/Batch 1/passwd');
    expect(res.status).toBe(400);
  });

  it('404s a batch that does not exist', async () => {
    const res = await request(app).get('/api/download/Batch 9999/x12');
    expect(res.status).toBe(404);
  });
});

/* -------------------------------------------------------------------------
 * The EDI2 Validator's read-only upload bridge (main). It shares createApp()
 * with the generator routes above and nothing else: a different Python entry
 * point, raw bytes rather than JSON, and never a write into the repo.
 * ---------------------------------------------------------------------- */

const BAD_I = path.join(
  REPO, 'edi2', 'batch1', 'UHCG_ECUSA_I_20260817174931.x12');
const GOLDEN_P_ADJUSTMENT = path.join(
  REPO, 'edi2', 'golden', 'professional-adjustment',
  'ADJ-UHCG_ERCT_P_20260730143200.x12');

function upload(target: ReturnType<typeof createApp>, body: Buffer,
                filename = 'UHCG_ECUSA_I_20260817174931.x12') {
  return request(target).post('/api/edi2/validate')
    .set('content-type', 'application/octet-stream')
    .set('x-edi-filename', filename)
    .send(body);
}

describe('read-only EDI2 uploads', () => {
  it('securely validates the returned Professional adjustment golden bytes', async () => {
    const bytes = await fsp.readFile(GOLDEN_P_ADJUSTMENT);
    const res = await upload(app, bytes, path.basename(GOLDEN_P_ADJUSTMENT));

    expect(res.status).toBe(200);
    expect(res.body.status).toBe('valid');
    expect(res.body.workflow.workflow).toBe('P');
    expect(res.body.coverage.professionalGolden).toBe('returned-adjustment');
    expect(res.body.summary).toMatchObject({ claims: 1, lines: 2, blockers: 0 });
    expect(res.body.adjudication.claims[0].adjustment.clm20.value).toBe('11');
    expect(res.body.adjudication.claims[0].lines).toHaveLength(2);
  });

  it('returns an invalid analysis as HTTP 200', async () => {
    const res = await upload(app, await fsp.readFile(BAD_I));

    expect(res.status).toBe(200);
    expect(res.body.status).toBe('invalid');
    expect(res.body.workflow.workflow).toBe('I');
    expect(res.body.summary.blockers).toBeGreaterThan(0);
  });

  it('rejects empty files and NUL bytes before spawning Python', async () => {
    expect((await upload(app, Buffer.alloc(0))).status).toBe(400);
    const nul = await upload(app, Buffer.from('ISA*00*\0PRIVATE~'));
    expect(nul.status).toBe(400);
    expect(nul.body.error).toMatch(/NUL/);
  });

  it('enforces a configurable raw upload ceiling', async () => {
    const small = createApp({ edi2: {
      maxUploadBytes: 32,
      runPython: async () => { throw new Error('must not spawn'); },
    } });

    const res = await upload(small, Buffer.alloc(33, 65));
    expect(res.status).toBe(413);
  });

  it('uses exec argument metadata safely and removes its temp directory', async () => {
    const tempRoot = await fsp.mkdtemp(path.join(os.tmpdir(), 'edi2-test-'));
    let observedArgs: string[] = [];
    const isolated = createApp({ edi2: {
      tempRoot,
      runPython: async (args) => {
        observedArgs = args;
        const input = args[args.indexOf('--file') + 1];
        expect((await fsp.stat(input)).isFile()).toBe(true);
        return JSON.stringify({
          status: 'valid',
          file: { filename: args[args.indexOf('--filename') + 1] },
        });
      },
    } });

    try {
      const res = await upload(
        isolated, Buffer.from('ISA*00*SAFE~'), '..\\..\\patient.x12');
      expect(res.status).toBe(200);
      expect(res.body.file.filename).toBe('patient.x12');
      expect(observedArgs[0]).toMatch(/validate_api\.py$/);
      expect(observedArgs).toContain('--file');
      expect(await fsp.readdir(tempRoot)).toEqual([]);
    } finally {
      await fsp.rm(tempRoot, { recursive: true, force: true });
    }
  });

  it('does not expose filesystem details when upload staging fails', async () => {
    const missingRoot = path.join(
      os.tmpdir(), `edi2-missing-${process.pid}-${Date.now()}`);
    const isolated = createApp({ edi2: {
      tempRoot: missingRoot,
      runPython: async () => { throw new Error('must not spawn'); },
    } });

    const res = await upload(isolated, Buffer.from('ISA*00*SAFE~'));
    expect(res.status).toBe(500);
    expect(res.type).toMatch(/json/);
    expect(res.body).toEqual({
      error: 'EDI2 validation could not be completed',
    });
    expect(res.text).not.toContain(missingRoot);
  });

  it('rejects compressed request bodies instead of inflating them', async () => {
    const isolated = createApp({ edi2: {
      runPython: async () => { throw new Error('must not spawn'); },
    } });
    const res = await request(isolated).post('/api/edi2/validate')
      .set('content-type', 'application/octet-stream')
      .set('content-encoding', 'gzip')
      .send(gzipSync(Buffer.from('ISA*00*SAFE~')));

    expect(res.status).toBe(415);
    expect(res.type).toMatch(/json/);
    expect(res.body.error).toMatch(/compressed/i);
  });

  it('rejects malformed JSON before the application JSON parser can leak', async () => {
    const res = await request(app).post('/api/edi2/validate')
      .set('content-type', 'application/json')
      .send('{PRIVATE INVALID JSON');

    expect(res.status).toBe(415);
    expect(res.type).toMatch(/json/);
    expect(res.body).toEqual({
      error: 'content-type must be application/octet-stream',
    });
    expect(res.text).not.toMatch(/SyntaxError|PRIVATE/);
  });

  it('fails safely when private upload cleanup cannot be confirmed', async () => {
    const tempRoot = await fsp.mkdtemp(path.join(os.tmpdir(), 'edi2-cleanup-'));
    let attempts = 0;
    const reportOperationalError = vi.fn();
    const isolated = createApp({ edi2: {
      tempRoot,
      runPython: async () => JSON.stringify({ status: 'valid' }),
      reportOperationalError,
      removeDirectory: async () => {
        attempts += 1;
        throw new Error(`PRIVATE ${tempRoot}`);
      },
    } });
    try {
      const res = await upload(isolated, Buffer.from('ISA*00*SAFE~'));
      expect(res.status).toBe(500);
      expect(res.body).toEqual({
        error: 'EDI2 validation could not be completed',
      });
      expect(res.text).not.toContain(tempRoot);
      expect(attempts).toBe(2);
      expect(reportOperationalError).toHaveBeenCalledWith(
        'EDI2 temporary upload cleanup failed');
    } finally {
      await fsp.rm(tempRoot, { recursive: true, force: true });
    }
  });

  it('cleans up and hides subprocess failures', async () => {
    const tempRoot = await fsp.mkdtemp(path.join(os.tmpdir(), 'edi2-runner-'));
    const isolated = createApp({ edi2: {
      tempRoot,
      runPython: async () => { throw new Error(`PRIVATE ${tempRoot}`); },
    } });
    try {
      const res = await upload(isolated, Buffer.from('ISA*00*SAFE~'));
      expect(res.status).toBe(500);
      expect(res.text).not.toContain(tempRoot);
      expect(await fsp.readdir(tempRoot)).toEqual([]);
    } finally {
      await fsp.rm(tempRoot, { recursive: true, force: true });
    }
  });

  it('reports cleanup failure even when validation already failed', async () => {
    const tempRoot = await fsp.mkdtemp(path.join(os.tmpdir(), 'edi2-both-'));
    const reportOperationalError = vi.fn();
    const isolated = createApp({ edi2: {
      tempRoot,
      runPython: async () => { throw new Error(`PRIVATE ${tempRoot}`); },
      removeDirectory: async () => { throw new Error(`PRIVATE ${tempRoot}`); },
      reportOperationalError,
    } });
    try {
      const res = await upload(isolated, Buffer.from('ISA*00*SAFE~'));
      expect(res.status).toBe(500);
      expect(res.text).not.toContain(tempRoot);
      expect(reportOperationalError).toHaveBeenCalledWith(
        'EDI2 temporary upload cleanup failed');
    } finally {
      await fsp.rm(tempRoot, { recursive: true, force: true });
    }
  });
});
