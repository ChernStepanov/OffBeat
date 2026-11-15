import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
const folder = 'data/benchmark/amazon-v1';
const hash = path => createHash('sha256').update(fs.readFileSync(path)).digest('hex');
const protocol = JSON.parse(fs.readFileSync(`${folder}/protocol.json`));
const results = JSON.parse(fs.readFileSync(`${folder}/results.json`));
for (const [path, expected] of Object.entries(protocol.input_sha256)) {
  assert.equal(hash(path), expected, `Frozen benchmark input changed: ${path}`);
}
assert.equal(hash(`${folder}/protocol.json`), results.protocol_sha256, 'Frozen protocol changed');
assert.equal(hash(`${folder}/evidence.json`), results.evidence_sha256, 'Evidence changed');
assert.equal(results.independent_test_events, 0);
for (const method of Object.values(results.methods)) {
  assert.equal(method.false_positive_rate, null);
  assert(method.independent_test.every(row => row.precision_at_k === null));
}
console.log('PASS: frozen benchmark receipts and explicitly unavailable independent accuracy');
