import assert from "node:assert/strict";
import test from "node:test";
import { isSentenceCommand, motionNames, shouldApplyImmediate } from "../../frontend/src/avatar_policy.ts";
import { faceWeights } from "../../frontend/src/vrm/expressions.ts";

test("sentence-level commands are queued, not immediate", () => {
  assert.equal(isSentenceCommand({ turn_id: "t1", sentence_idx: 0 }), true);
  assert.equal(isSentenceCommand({ turn_id: "t1", sentence_idx: 0, immediate: true }), false);
  assert.equal(isSentenceCommand({ expression: "thinking", immediate: true }), false);
});

test("motion and stop punch through sentence hold", () => {
  assert.equal(shouldApplyImmediate({ motions: ["wave"], immediate: true }, true), true);
  assert.equal(shouldApplyImmediate({ control: "stop", immediate: true }, true), true);
  assert.equal(shouldApplyImmediate({ expression: "listening", immediate: true }, true), false);
  assert.equal(shouldApplyImmediate({ expression: "thinking", immediate: true }, true), false);
  assert.equal(shouldApplyImmediate({ expression: "listening", immediate: true }, false), true);
});

test("motionNames prefers motions list", () => {
  assert.deepEqual(motionNames({ motion: "nod", motions: ["wave", "bow"] }), ["wave", "bow"]);
  assert.deepEqual(motionNames({ motion: "nod" }), ["nod"]);
});

test("shy and thinking are not the same face", () => {
  const shy = faceWeights("shy");
  const thinking = faceWeights("thinking");
  assert.ok((shy.relaxed ?? 0) > (thinking.relaxed ?? 0));
  assert.ok((thinking.lookUp ?? 0) > 0);
  assert.equal(thinking.lookDown ?? 0, 0);
});
