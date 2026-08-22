/**
 * The bridge's own contract: argument refusals it owns, and the generator's
 * refusals it must forward rather than swallow.
 *
 * Nothing here generates a file. A real POST /api/generate would draw
 * identifiers out of the repo's masterfile, which is exactly the side effect
 * the generator exists to make permanent - so the happy path is proven in
 * the browser (task 13), not by a test that would spend real identifiers on
 * every run.
 */
import { describe, expect, it, vi } from 'vitest';
import request from 'supertest';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { gzipSync } from 'node:zlib';
import { createApp, REPO } from './api';

const app = createApp();
const BAD_I = path.join(
  REPO, 'edi2', 'batch1', 'UHCG_ECUSA_I_20260817174931.x12');

function upload(target: ReturnType<typeof createApp>, body: Buffer,
                filename = 'UHCG_ECUSA_I_20260817174931.x12') {
  return request(target).post('/api/edi2/validate')
    .set('content-type', 'application/octet-stream')
    .set('x-edi-filename', filename)
    .send(body);
}

describe('argument refusals', () => {
  it('rejects a transaction type that is not I or P', async () => {
    const res = await request(app).post('/api/generate')
      .send({ type: 'D', claims: 1, overrides: {} });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/type must be I or P/);
  });

  it('rejects a claim count outside 1..200', async () => {
    const res = await request(app).post('/api/generate')
      .send({ type: 'I', claims: 201, overrides: {} });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/claims must be 1\.\.200/);
  });

  it('rejects a non-integer claim count', async () => {
    const res = await request(app).post('/api/generate')
      .send({ type: 'I', claims: 2.5, overrides: {} });
    expect(res.status).toBe(400);
  });

  it('rejects a download kind that is not x12 or docx', async () => {
    const res = await request(app).get('/api/download/2/pdf');
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/kind must be x12 or docx/);
  });

  it('404s a batch id that no run holds', async () => {
    const res = await request(app).get('/api/download/999999/x12');
    expect(res.status).toBe(404);
  });
});

describe('the generator speaks for itself', () => {
  it("forwards the generator's own message for a bad override", async () => {
    const res = await request(app).post('/api/generate')
      .send({ type: 'I', claims: 1, overrides: { claims: [{ n: 99 }] } });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/outside the batch/);
  });

  it('refuses a bad type before spawning anything', async () => {
    const res = await request(app).get('/api/defaults?type=D');
    expect(res.status).toBe(400);
  });
});

describe('reads that allocate nothing', () => {
  it('serves the seed defaults as an override document', async () => {
    const res = await request(app).get('/api/defaults?type=I');
    expect(res.status).toBe(200);
    expect(res.body.identity.subscriber.memberId).toMatch(/^\d+$/);
    expect(Array.isArray(res.body.claims)).toBe(true);
  });

  it('serves the identifiers a run would take', async () => {
    const res = await request(app).get('/api/masterfile?type=I&claims=3');
    expect(res.status).toBe(200);
    expect(res.body.isa13).toMatch(/^\d{9}$/);
    expect(res.body.st02).toHaveLength(3);
    expect(res.body.nextBatch).toBeGreaterThan(0);
  });

  it('peeking twice gives the same answer', async () => {
    const first = await request(app).get('/api/masterfile?type=P&claims=2');
    const second = await request(app).get('/api/masterfile?type=P&claims=2');
    expect(first.body).toEqual(second.body);
  });

  it('lists history newest first, without the imported pseudo-run', async () => {
    const res = await request(app).get('/api/history');
    expect(res.status).toBe(200);
    for (const run of res.body) {
      expect(run.type === 'I' || run.type === 'P').toBe(true);
      // batchId indexes the runs array, so it must survive the filter.
      expect(run.batchId).toBeGreaterThan(0);
    }
    const ids = res.body.map((r: { batchId: number }) => r.batchId);
    expect([...ids]).toEqual([...ids].sort((a, b) => b - a));
  });

  it('downloads the .x12 of a real past batch', async () => {
    const history = await request(app).get('/api/history');
    const batchId = history.body[0]?.batchId;
    expect(batchId).toBeGreaterThan(0);
    // .x12 has no registered media type, so supertest hands back a Buffer
    // rather than parsed text.
    const res = await request(app).get(`/api/download/${batchId}/x12`)
      .buffer(true).parse((r, cb) => {
        const chunks: Buffer[] = [];
        r.on('data', (c: Buffer) => chunks.push(c));
        r.on('end', () => cb(null, Buffer.concat(chunks)));
      });
    expect(res.status).toBe(200);
    expect(res.headers['content-disposition']).toContain('.x12');
    expect((res.body as Buffer).toString('ascii')).toContain('ISA*00*');
  });
});

describe('read-only EDI2 uploads', () => {
  it('returns an invalid analysis as HTTP 200', async () => {
    const res = await upload(app, await fs.readFile(BAD_I));

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
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'edi2-test-'));
    let observedArgs: string[] = [];
    const isolated = createApp({ edi2: {
      tempRoot,
      runPython: async (args) => {
        observedArgs = args;
        const input = args[args.indexOf('--file') + 1];
        expect((await fs.stat(input)).isFile()).toBe(true);
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
      expect(await fs.readdir(tempRoot)).toEqual([]);
    } finally {
      await fs.rm(tempRoot, { recursive: true, force: true });
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
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'edi2-cleanup-'));
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
      await fs.rm(tempRoot, { recursive: true, force: true });
    }
  });

  it('cleans up and hides subprocess failures', async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'edi2-runner-'));
    const isolated = createApp({ edi2: {
      tempRoot,
      runPython: async () => { throw new Error(`PRIVATE ${tempRoot}`); },
    } });
    try {
      const res = await upload(isolated, Buffer.from('ISA*00*SAFE~'));
      expect(res.status).toBe(500);
      expect(res.text).not.toContain(tempRoot);
      expect(await fs.readdir(tempRoot)).toEqual([]);
    } finally {
      await fs.rm(tempRoot, { recursive: true, force: true });
    }
  });

  it('reports cleanup failure even when validation already failed', async () => {
    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'edi2-both-'));
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
      await fs.rm(tempRoot, { recursive: true, force: true });
    }
  });
});
