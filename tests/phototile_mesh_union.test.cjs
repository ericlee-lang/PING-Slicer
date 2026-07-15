"use strict";

const assert = require("node:assert/strict");
const {
  cleanIsolated,
  smoothLabelNoise,
  filterSmallComponents,
  collectParts,
  buildLabelMesh,
  auditMesh
} = require("../resources/web/phototile/mesh_union.js");

function flatten(rows) {
  return new Uint8Array(rows.flat());
}

function verifyMask(name, rows, paletteSize, expectedComponents) {
  const h = rows.length;
  const w = rows[0].length;
  const labels = flatten(rows);
  const collected = collectParts(labels, w, h, paletteSize);
  assert.equal(collected.components, expectedComponents.reduce((a, b) => a + b, 0), `${name}: total components`);

  for (let k = 0; k < paletteSize; k++) {
    const part = collected.parts.find(item => item.k === k);
    const cells = Array.from(labels).filter(value => value === k).length;
    if (!cells) {
      assert.equal(part, undefined, `${name}: unused label ${k}`);
      continue;
    }
    assert.ok(part, `${name}: missing label ${k}`);
    const mesh = buildLabelMesh(labels, w, h, k, part.runs, 0.1, 0.1, 6);
    const audit = auditMesh(mesh);
    assert.equal(audit.boundaryEdges, 0, `${name}: label ${k} has open edges`);
    assert.equal(audit.nonManifoldEdges, 0, `${name}: label ${k} has non-manifold edges`);
    assert.equal(audit.components, expectedComponents[k], `${name}: label ${k} shell count`);
    assert.ok(audit.signedVolume > 0, `${name}: label ${k} winding`);
    assert.ok(Math.abs(audit.signedVolume - cells * 0.1 * 0.1 * 6) < 1e-8, `${name}: label ${k} volume`);
  }
}

verifyMask("solid", [
  [0, 0],
  [0, 0]
], 1, [1]);

verifyMask("L shape", [
  [0, 1],
  [0, 0]
], 2, [1, 1]);

verifyMask("hole", [
  [0, 0, 0],
  [0, 1, 0],
  [0, 0, 0]
], 2, [1, 1]);

verifyMask("diagonal islands", [
  [0, 1],
  [1, 0]
], 2, [2, 2]);

verifyMask("three labels", [
  [0, 0, 1, 1],
  [0, 1, 1, 1],
  [2, 2, 1, 0]
], 3, [2, 1, 1]);

const isolated = flatten([
  [0, 0, 0],
  [0, 1, 0],
  [0, 0, 0]
]);
assert.deepEqual(Array.from(cleanIsolated(isolated, 3, 3)), new Array(9).fill(0), "isolated pixel cleanup");

const bridge = flatten([
  [0, 0, 0, 0, 0],
  [1, 1, 1, 1, 1],
  [0, 0, 0, 0, 0]
]);
assert.deepEqual(Array.from(cleanIsolated(bridge, 5, 3)), Array.from(bridge), "one-pixel bridge must be preserved");

const bridgeNoiseRows = Array.from({ length: 21 }, () => new Array(21).fill(0));
for (let y = 6; y <= 14; y++) for (let x = 0; x <= 6; x++) bridgeNoiseRows[y][x] = 1;
for (let x = 7; x <= 17; x++) bridgeNoiseRows[10][x] = 1; // thin bridge makes this one large connected component
const componentOnlyBridge = filterSmallComponents(flatten(bridgeNoiseRows), 21, 21, 0.1, 0.1, 0.5);
assert.equal(componentOnlyBridge.labels[10 * 21 + 17], 1, "component-only filtering demonstrates the thin-bridge regression");
const bridgeNoise = smoothLabelNoise(flatten(bridgeNoiseRows), 21, 21, 2, 0.1, 0.1, 0.5, "median");
assert.equal(bridgeNoise.labels[10 * 21 + 17], 0, "median smoothing removes a speck joined to a major region by a thin bridge");
assert.equal(bridgeNoise.labels[10 * 21 + 3], 1, "median smoothing preserves the major region");

const pinholeRows = Array.from({ length: 9 }, () => new Array(9).fill(1));
pinholeRows[4][4] = 0;
const pinhole = smoothLabelNoise(flatten(pinholeRows), 9, 9, 2, 0.1, 0.1, 0.5, "median");
assert.equal(pinhole.labels[4 * 9 + 4], 1, "median smoothing fills a small pinhole");

const smoothingDisabledSource = flatten([
  [0, 0, 0],
  [0, 1, 0],
  [0, 0, 0]
]);
const smoothingDisabled = smoothLabelNoise(smoothingDisabledSource, 3, 3, 2, 0.1, 0.1, 0, "median");
assert.deepEqual(Array.from(smoothingDisabled.labels), Array.from(smoothingDisabledSource), "zero disables label smoothing");

function filterRows(rows, thresholdMm, sx = 0.1, sz = 0.1) {
  return filterSmallComponents(flatten(rows), rows[0].length, rows.length, sx, sz, thresholdMm);
}

const onePixelRows = Array.from({ length: 25 }, () => new Array(25).fill(0));
onePixelRows[12][12] = 1;
const onePixel = filterRows(onePixelRows, 2);
assert.deepEqual(Array.from(onePixel.labels), new Array(625).fill(0), "2 mm filter removes a one-pixel island");
assert.equal(onePixel.removedComponents, 1, "one island is reported");
assert.equal(onePixel.changedPixels, 1, "one changed cell is reported");
assert.ok(Math.abs(onePixel.changedAreaMm2 - 0.01) < 1e-12, "changed physical area is reported");

const exactRows = Array.from({ length: 5 }, () => new Array(24).fill(0));
for (let x = 2; x < 22; x++) exactRows[2][x] = 1; // 20 cells = exactly 2.0 mm
const exactTwoMm = filterRows(exactRows, 2);
assert.ok(Array.from(exactTwoMm.labels).every(value => value === 0), "exactly 2.0 mm is included in the filter");

const overRows = Array.from({ length: 5 }, () => new Array(25).fill(0));
for (let x = 2; x < 23; x++) overRows[2][x] = 1; // 21 cells = 2.1 mm
const overTwoMm = filterRows(overRows, 2);
assert.equal(Array.from(overTwoMm.labels).filter(value => value === 1).length, 21, "a 2.1 mm island is preserved");
assert.equal(overTwoMm.changedPixels, 0, "over-threshold island is unchanged");

const disabled = filterRows([
  [0, 0, 0],
  [0, 1, 0],
  [0, 0, 0]
], 0);
assert.deepEqual(Array.from(disabled.labels), [0,0,0,0,1,0,0,0,0], "zero disables filtering");

const nestedRows = Array.from({ length: 9 }, () => new Array(9).fill(0));
for (let y = 3; y <= 5; y++) for (let x = 3; x <= 5; x++) nestedRows[y][x] = 1;
nestedRows[4][4] = 2;
const nested = filterRows(nestedRows, 0.5);
assert.ok(Array.from(nested.labels).every(value => value === 0), "nested small islands are removed over successive passes");
assert.equal(nested.removedComponents, 2, "nested cleanup reports both components");

const thinRows = Array.from({ length: 5 }, () => new Array(34).fill(0));
for (let x = 2; x < 32; x++) thinRows[2][x] = 1; // only 0.1 mm thick, but 3.0 mm long
const longThin = filterRows(thinRows, 2);
assert.equal(Array.from(longThin.labels).filter(value => value === 1).length, 30, "long thin detail uses its longer side and is preserved");

let seed = 0x5eed1234;
function random() {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed / 0x100000000;
}
for (let sample = 0; sample < 40; sample++) {
  const w = 3 + (sample % 6);
  const h = 3 + (sample % 5);
  const labels = new Uint8Array(w * h);
  for (let i = 0; i < labels.length; i++)
    labels[i] = Math.floor(random() * 3);
  const collected = collectParts(labels, w, h, 3);
  for (const part of collected.parts) {
    const mesh = buildLabelMesh(labels, w, h, part.k, part.runs, 0.1, 0.1, 6);
    const audit = auditMesh(mesh);
    const cells = Array.from(labels).filter(value => value === part.k).length;
    assert.equal(audit.boundaryEdges, 0, `random ${sample}: label ${part.k} open edges`);
    assert.equal(audit.nonManifoldEdges, 0, `random ${sample}: label ${part.k} non-manifold edges`);
    assert.equal(audit.components, part.components, `random ${sample}: label ${part.k} components`);
    assert.ok(Math.abs(audit.signedVolume - cells * 0.1 * 0.1 * 6) < 1e-8, `random ${sample}: label ${part.k} volume`);
  }
}

console.log("phototile mesh union tests: PASS");
