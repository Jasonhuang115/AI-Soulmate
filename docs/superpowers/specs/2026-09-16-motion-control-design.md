# 动作与表情控制

日期：2026-09-16  
状态：按本文件实现。对照仓库计划「动作与表情控制系统」。

阿澄用句内 `⟦marker⟧` 表达态度和身体动作。Harness 机械解析并执行。不走 function calling。模型在稳定 system 块里看见全部动作名。

## 1. 标记

只认三类，名字来自 `frontend/public/gestures/catalog.json` 与 `embodiment/vocab.py`：

- 态度：`neutral happy shy sad surprised angry thinking playful agree disagree`
- 动作：catalog 里每一个具体 key（约 100 个）。**不要把 group 当标记**（`dance` / `greet` / `think` 已是片子）。
- 控制：`stop`（停身体，脸不变）

句内连写最多 3 个动作 = 序列。未知标记丢弃，追加 `data/logs/unresolved_markers.jsonl`。

## 2. 时机

`_TurnEmitter` 维护「当前句是否已有正文」和「上一句是否刚结束」。

- 回合开头、尚无任何句子：标记立刻 `immediate=True`（用户点名挥手）。
- 一句已结束、下一批是正文：这中间的动作标记也是下一句的句首，立刻执行。
- 回合结束仍挂着、没有后续正文：当作上一句的句末，绑 `sentence_idx`，跟 TTS 开播。
- 句中出现的标记：句末，绑当前句。

态度写在句末，跟这句语音对齐。动作默认不写；用户明确要求时写在该句第一个字之前。

前端 `shouldApplyImmediate`：`motions` / `stop` 的 immediate 一律执行。仅有 listening/thinking 的状态脸在 `sentenceHold` 时让路。

## 3. 提示词

`03-tools.md` 列出全部态度和全部分组动作（标记 + 短说明）。用法：

- 每句尽量句末一个态度。
- 默认不写动作。用户点名必须句首写对应动作。
- 跑、爬、翻滚、太空步等除非点名不要用。

`01-soul.md` 不写「动作只能句末」。

## 4. catalog

每条动作：

- `kind`: `gesture` | `pose` | `loop` | `transition`
- `desc` / `label`: 进提示词的短说明
- `aliases`: 可选，英文变体，只给 resolve，不扫用户中文
- `face`: 可选，无显式态度时的脸
- `holds`: pose 进入后循环的片子
- `group`: 提示词分组

`prompt` / `phase` 不再决定是否进提示词。全部动作进 `MOTIONS`。

姿态：`sit` / `sit_down` / `kneel` / `crouch` / `lie_down`。过渡：`stand_up` / `stand`。v1 姿态独占：坐下时忽略全身 gesture，直到 `stand_up` 或 `stop`。

## 5. 协议

`AvatarCommand`：`expression`, `motions: tuple[str, ...]`, `control`, `intensity`（预留）, `immediate`。WebSocket 同时带 `motion`（首个）和 `motions` 以免旧前端崩。

内部仍发 `ToolCall(name="set_emotion")`。`EmbodimentService.tools()` 为空。不在 `StartTurn` 上正则猜动作。

## 6. 前端

启动加载人模后一口气预载全部 `.vrma` 并 `createVRMAnimationClip`。未齐时动作命令排队。换 `.vrm` 重建。

`motion_runtime.ts`：idle / pose / loop / gesture。pose 期间 gesture 忽略。`stop` 清队列回 idle，不动脸。

`expressions.ts`：逻辑名 → preset 权重。`shy` 与 `thinking` 不再都等于单纯 `relaxed`。
