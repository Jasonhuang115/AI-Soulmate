import assert from "node:assert/strict";
import test from "node:test";
import { expressionNames, isSentenceCommand, shouldApplyImmediate } from "../../frontend/src/avatar_policy.ts";

test("expression names include model json aliases", () => {
  assert.deepEqual(expressionNames("f02.exp.json"), ["f02.exp.json", "f02", "f02.exp"]);
});

test("sentence-level commands are queued, not immediate", () => {
  assert.equal(isSentenceCommand({ turn_id: "t1", sentence_idx: 0 }), true);
  assert.equal(isSentenceCommand({ turn_id: "t1", sentence_idx: 0, immediate: true }), false);
  assert.equal(isSentenceCommand({ expression: "thinking", immediate: true }), false);
});

test("idle and listening do not clobber a held sentence face", () => {
  assert.equal(shouldApplyImmediate({ expression: "neutral", immediate: true }, true), false);
  assert.equal(shouldApplyImmediate({ expression: "listening", immediate: true }, true), true);
  assert.equal(shouldApplyImmediate({ expression: "thinking", immediate: true }, true), true);
  assert.equal(shouldApplyImmediate({ expression: "neutral", immediate: true }, false), true);
});
