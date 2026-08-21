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
import { describe, expect, it } from 'vitest';
import request from 'supertest';
import { createApp } from './api';

const app = createApp();

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
