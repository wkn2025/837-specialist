// @vitest-environment node
/**
 * Task 10: the bridge is the only thing between the browser and a CLI that
 * allocates never-reused identifiers. Every test that could allocate runs
 * against a throwaway copy of EDI1/, the same way the Python CLI tests do.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import request from 'supertest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
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
