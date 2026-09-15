# 开源虚拟陪伴调研：记忆 × 类脑心情 × 主动开口

日期：2026-09-14  
范围：对照 [awesome-ai-companion](https://github.com/DasterProkio/awesome-ai-companion) 与同赛道项目，抽出**机制级**细节（字段、公式、文件布局、prompt 片段），给 ASM 当作业。  
来源：各仓库 README / 源码 / 官方文档，不是项目名联想。  
对照对象：ASM 已有事件总线 harness、文件型 memory agent（`ls/read/grep/write_section/append`）、`data/memory/`、dream 门控（24h + 5 会话）、impulse 三种触发（开场 / 到期回访 / 空闲 30% 骰子）。

**对 ASM 的总判断**

- 实时对话 + Live2D + 文件记忆这条线和 Warashi、Elino、VAPE、Meux、Soul-of-Waifu 同一类。
- 别人更重向量检索、遗忘曲线、关系数值养成；ASM 更重 harness 干净和语音实时性。
- 记忆骨架（文件 + grep、对话模型不直接改主题文件、dream 巩固）已经对齐 Claude Code / Letta sleeptime，不必换成向量库。
- 目前最不像人的缺口是 **impulse 用随机骰子、`self_state.md` 不会自己变**，不是「没有记忆模块」。

---

## 目录

1. [记忆系统（12 个项目 + Claude Code）](#1-记忆系统)
2. [心情、驱力、主动开口（14 个项目）](#2-心情驱力主动开口)
3. [跨项目共性](#3-跨项目共性)
4. [对 ASM 的可抄清单](#4-对-asm-的可抄清单)
5. [明确不抄](#5-明确不抄)

---

## 1. 记忆系统

### 1.1 Project-elino（Tacky7788/Project-elino）

桌面 Live2D/VRM，数据在 `%APPDATA%/elino/companion/`：`memory.json` + `state.json` + `history.jsonl`，向量缓存单独文件（`paraphrase-multilingual-MiniLM-L12-v2`）。

**分层（`memoryV2` 一个 JSON 里的字段）**

- `facts`：用户事实，key 形如 `likes|coffee` / `profile|job` / `event|…` / `skill|…` / `opinion|…` / `relation|…`
- `summaries`：对话摘要，最多 10 条
- `relationship`：`firstMet`、`interactionCount`、`episodes[]`（最多 50，type=bonding/neutral）、`emotions`
- `topics`：recent / favorites / avoided / mentioned 计数，提及 ≥5 次进 favorites
- `promises[]`：含 `open_loop`
- `impressions`

**写入**：每轮后 `ipc-memory-apply.cjs` 调 LLM 一次抽出 JSON：`facts / promise / episode / openLoop / topics / emotionDimensions / fulfilledPromises / impression`。Prompt 要求 `emotionDimensions` 是本轮感受，不是累积值。

**注入**（`prompt-builders.cjs::buildStateLayer`）：facts 按 retention 打把握度标记——≥0.7 无标记，≥0.4 `(pretty sure)`，≥0.2 `(maybe)`，否则 `(fuzzy memory)`。关系距离由 interactionCount / 天数 / 是否有 bonding 决定三档语气。摘要取最近 5 条 + 关键词匹配 3 条。

**类脑**

- 遗忘：`retention = e^(-tDays / stability)`，`stability = (1.0 + recallCount*0.2) / decayRate`，`decayRate = max(0.1, 1 - |valence-0.5|*2*0.5)`（情绪越强越难忘）。
- 混合排序：`score = RRF(bm25Rank, vectorRank, k=60)*200 + retention*1.5 + importance{high:1, medium:.6, low:.3} + freshness(60天线性)*0.5 + min(0.3, seenCount*0.05)`。
- 6 轴情绪（valence / arousal / dominance / trust / fatigue + curiosity；代码里还有 uncertainty / surprise / boredom），EMA 平滑，trust 系数 0.12（慢），valence 0.3（快）。`brain-tick` 定时 `decayEmotions` 与 `decayRecallScores`。
- 前瞻：`promises` + `openLoop`，静默期由 `decideAction` 触发 `open_loop_followup`。
- 钉选事实不衰减。

README 对外宣传的四层是 Facts / Summaries / Relationship / Emotional State，和源码字段对应但更粗。

### 1.2 MeuxCompanion（meet447/MeuxCompanion）

角色层：`character.yaml` + `soul.md` + `style.md` + `rules.md` + `context.md` + `examples/chat_examples.md`。和 ASM 的 `prompts/01-soul.md` / `02-medium.md` / `03-tools.md` 同构。

**记忆（后期文档，已替换早期 semantic/episodic/reflection 三分）**

- Facts：关于用户的持久陈述，上限 300
- Moments：每轮一句带日期与伴侣感受，`weight` 默认 0.5，同轮改 mood/closeness 则 0.8
- Bond：`closeness` 0–1、`mood{name,intensity,cause,wants,since}`、`threads[]` 开放话题 ≤8、`last_talked_at`
- Session：近期转录，非长期记忆

存储：`data/users/{user}/companions/{char}/profile.json + moments.jsonl + bond.json`，并投影成 markdown 给 agent 读。

**写入**：agent 在回复末尾输出隐藏块 `<<<meuxe {"remember":[…],"moment":"…","mood":{…},"closeness":1,"open_threads":[…],"closed_threads":[…]} >>>`，Rust 端剥离后在**确定性护栏**下应用，不从用户文本推断。事实去重：归一化文本 + token Jaccard ≥0.8 视为同一条，刷新 `confirmed_at/mentions`。

**注入顺序**：`## How you feel right now`（阶段、亲密度、距上次、mood 原因/期望、open threads）→ `## What you know about {user}` → `## Moments`（最近 4 条 + 词重叠 3 条）。

**护栏（硬编码，最值得看）**

- closeness 每轮 +0.002 基线，agent 可 ±2 步（每步 0.015）；14 天沉默后每日 −0.005，下限 0.1；阶段阈值 0.15 / 0.35 / 0.6 / 0.85
- 负面 mood 每 48h 减半，正面每 12h 减半，&lt;0.15 归 neutral；负面未处理就消退时，cause 转为 open thread
- 「不许瞬间原谅」：负面 intensity&gt;0.45 时，agent 提议正面 mood 只降 0.35，需 2–3 轮化解
- 缺席 ≥5 天且 closeness≥0.35 → mood 变 "missed you"（0.3，每多一周 +0.1，上限 0.6）
- 路线图：90 天以上 moments 夜间合并成摘要

早期架构文档还写过 `episodic.jsonl` / `semantic.jsonl` / `reflections.jsonl` / `state.json`（trust, affection, mood, energy）。PR #41 加过 SQLite vault + dream reflections + pin/forget + FTS。

### 1.3 Warashi（inni918/warashi）

Open-LLM-VTuber 套壳。设计见 `MEMORY_SYSTEM_DESIGN.md`，代码 `src/open_llm_vtuber/memory_core.py`。

- 每角色一份 `chat_history/<conf_uid>/core_memory.md`，默认 cap **1500 字**（可调 500–8000）
- 注入：`construct_system_prompt` 附到 persona 后，改完即时生效
- 可选 FTS5 trigram 深搜全历史
- 每轮（或每 3/5 轮）后台 fire-and-forget 整理

**整理 prompt 原文规则（可当 extract 模板）**

- 只记：使用者事实（身分／职业／正在做的事）、偏好与习惯、希望被怎么称呼、重要事件或对话结论
- 绝不记：一次性闲聊、寒暄、问候、没有新资讯的对话、AI 自己说的话
- 没有值得记的新信息 → 原封不动输出现有记忆
- 超 cap 则合并提炼，保留最关键、删过时细节

无衰减、无情绪打标、无梦境。等于 Letta core memory block 的极简版。

### 1.4 VAPE（syahiidkamil/vibe-ai-partner-entity）

跑在 Claude Code / Codex 上，明文文件 + git。卖点是「明天还记得一起过的日子」。

**自我分层（越深越难改）**：`01_fixed` → `02_singularity_self`（改动需 gate）→ `03_self_creation_self` → `04_values` → `05_relational_self` → `06_temporal_self_and_soul`（日/周/月/年切片，每天覆写，git 留史）。

**记忆分层**

- HOT `memory/in_context/`：常驻 living keys、goals、**prospective intentions**、active lessons、self-critique、三张 dot networks
- WARM wiki：`notes/` 收件箱、`schemata/` 世界模型、`cases/`、`skills_in_memory/`、`decisions/`、`suffering/`、`people/`、`events/`、`archive/`、`dreams/`、diary
- COLD `storage/YYYY/MM/`：每轮原始 chat + qualia（hook 捕获，gitignore）

**两个门**

1. **affect + surprise 书签**：情绪尖峰或她主动 flag 才进记忆
2. 夜间 dream 按 **forward viability**（帮不帮明天的我）决定去留

日记必须在 `/compact` 或 `/clear` 前写（`/write-or-update-personal-diary`）。dream **只能对人设提案**，醒时 `/ask:self-update-proposal-review`，用户 commit 才批准。有意遗忘带 exit interview。检索是可丢弃插件（SQLite FTS / sqlite-vec / pgvector / qmd）。

### 1.5 Ombre-Brain（P0luz/Ombre-Brain）

给 Claude 用的长期情绪记忆。每条记忆 = 一个 Obsidian Markdown + YAML frontmatter。MCP 工具：`breath` / `hold` / `grow` / `trace` / `pulse` / `dream`。

**桶类型**：`dynamic`（衰减）/ `permanent`（pinned，importance 锁 10）/ `feel`（模型自省，不浮现不衰减不合并）/ `archived`。

**frontmatter 字段**：`id, name, tags, domain, valence, arousal, model_valence, importance(1-10), activation_count, resolved, digested, pinned, created, last_active`。

**衰减（`INTERNALS.md` / `decay_engine.py`）**

```
Score = Importance × activation_count^0.3 × e^(-λ×days) × combined_weight
λ = 0.05，归档阈值 0.3
≤3 天：时间 70% + 情感 30%
>3 天：情感 70% + 时间 30%
新鲜度：1 + e^(-t/36h)，刚存入 ×2，~36h 半衰
arousal>0.7 且未 resolved → ×1.5
resolved → ×0.05；resolved+digested → ×0.02
importance≤4 且 >30 天 → 自动 resolved
```

**检索**

- 无 query 浮现：钉选常驻 + 冷启动（activation_count==0 且 importance≥8）最多 2 条置顶 + Top-1 固定 + Top-20 随机打乱，token 预算 10000
- 有 query：topic×4 + emotion×2 + time×2.5 + importance×1
- 结果 &lt;3 条时 40% 概率漂 1–3 条低分旧桶（随机联想）
- 查询带 valence 时展示层偏移 ±0.1（情感记忆重构，原值不改）

**其他**：touch 一条时 ±48h 邻条 `activation_count += 0.3`（时间涟漪 / 扩散激活）；≥3 条相似 feel（&gt;0.7）提示结晶为钉选准则。对话启动：`breath() → dream() → breath(domain="feel")`。

Fork Haven-Ombre 加了 persona、handoff、Darkroom、Dream、自动写入门卫。

### 1.6 kiwi-mem（LucieEveille/kiwi-mem，及若干 fork）

Python/FastAPI + PostgreSQL + pgvector，插在 LLM 前面的记忆网关。AGPL。

**热度**

```
initial_temp = 0.3 + 0.7 × max(importance/10, emotional_weight/10)
half_life = (3天 | importance≥8 或 emo≥6 时 7天) × (1 + access_count × 0.5)
decay = 2^(-age / half_life)
recall_bonus = min(0.2, access_count×0.02 + query_diversity×0.03)
heat = initial_temp × decay + recall_bonus
```

- **只有真正写进 prompt 才算一次召回**
- 热度分档：&gt;0.7 全文；0.3–0.7 摘要并标「印象模糊」；更低不注入
- 自动锁定：access≥10 且 query_diversity≥5（高情绪门槛更低）；90 天未召回可从永久降回普通（不删除）
- **soften**：夜间去掉细节、保留情感与结论；软化后续命 30 天

**Dream 三层 prompt**：「你刚刚睡着了」→ 整理（过时/重复/矛盾）→ 固化碎片为 MemScene → 生长 Foresight（带 `valid_until`）。动作：`delete/merge/soften/promote/create_scene/update_scene/update_profile/link`。边类型：`extends/supersedes/contradicts/resonates_with/references`。触发：手动 / 犯困 / 24h 无活动。

日历：日 → 周 → 月 → 季 → 年套娃注入。静态区在前打 prompt cache。矛盾则旧记忆 `valid_until` 失效。

### 1.7 Memory Constellations 记忆星图（ClaraShafiq/MemoryConstellations）

自组织管线。Scribe / Archivist / Librarian。积温是可选的情绪侧车，和记忆解耦。

**层**

| 层 | 内容 | 更新 |
| --- | --- | --- |
| Fragments | ≤80 字第三人称单事实，类型 observation/reflection/preference/event/state | 静默 ≥20min 或积压 ≥100 条 |
| Entities | 人/地/事/爱好/项目；三字段 facts（覆盖）/ current_status（覆盖）/ judgment（演化，旧值作参考） | Archivist |
| Episodes | 100–250 字叙事，日期校正 + 矛盾检测 | 用户空闲 ≥1h 的 Deep cycle |
| Sagas | 跨实体叙事弧（实验，生产未消费） | 24h 或新 episode |

用户模型三层：`current_state`（TTL 瞬态）/ `current_status`（近期动态）/ `user_patterns`（行为模式，**置信度只增不减**，新鲜度独立控制注入）。伴侣自我在 `persona_model`。

**引用权限（确定性，不调模型）**

- 双通道命中且 &lt;30 天 → **可引用**
- 单通道或 30–90 天 → **需谨慎**（「我好像记得…」）
- &gt;90 天或随机漂浮 → **仅联想**（不对用户当事实说）

衰减分段同 Ombre：≤3 天新鲜度主导，&gt;3 天情绪主导。Fragments 14 天无访问 → cooling → 30 天删向量 → 90 天擦内容，访问即复活。`manage_user_state` 支持带 schedule 的周期提醒。`correct_memory` 回溯改源碎片。Librarian：FTS5 + 向量 + 实体聚合，RRF，episode 权重 ×1.5。

### 1.8 Soul-of-Waifu（jofizcd/Soul-of-Waifu）

文件布局几乎就是 ASM 该长成的样子。路径 `.soul/{character}/{chat_id}/memory/`：

- `MEMORY.md`：心理。`core_identity`、`internal_state{primary_emotion, intensity 1–5, psychological_tension, emotional_decay_counter}`、`cognitive_drive{active_agenda, immediate_focus}`、`cognitive_dissonance`
- `USER.md`：关系。role、known_attributes、trust_level 枚举（Distrustful → Deeply Bound / Unstable）、unspoken_tension、preferences_habits、shared_milestones_promises
- `topics/*.md`：情节知识，每文件 &lt;300 字
- `DIARY.md`：第一人称 4–6 句反思

三子 agent：Router 改 MEMORY/USER（可 `{"no_significant_change": true}` 空操作）→ Archivist 写 topic（冲突直接覆盖）→ Diary。同步模式 Full Sync / Soul Link / Mind Spark / Reflection Flow，每 1/5/10/20 条触发。TopicRAG：topic ≤4 全量，否则本地 `all-MiniLM-L6-v2` top-3。

**情绪衰减计数器**：连续 3 轮未再提及该情绪则软化/过渡；被提及则 reset 为 0。`healing_log` 记被修正的矛盾。

### 1.9 Letta / MemGPT sleeptime

- core = 上下文内 memory blocks（`persona` / `human` / 自定义），可只读、可多 agent 共享
- recall = 对话历史；archival = 显式保存的向量记忆
- `enable_sleeptime=True`：主 agent **没有** 改 core 的工具；睡眠 agent 持有 `memory_insert / memory_replace / memory_rethink / memory_finish_edits`
- 频率默认每 5 条消息；新版 MemFS 可 git 版本化
- 无情绪、无衰减。论文概念：Sleep-time Compute

### 1.10 Paramecium（Shitsuten/paramecium）

**明确拒绝**遗忘曲线 / 情绪打分 / 梦境（相关代码进 `attic/`）。

- L0 原文：逐字存档，机械切窗 ≤700 字，bge-small-zh + FTS5
- L1 摘录：便宜模型圈 ≤5 个信息点，**每条必须附 10–40 字逐字引用**，校验不在原文则整条丢弃
- L2 画像：手工 markdown `profile/facts/`，全文进缓存段

L1 只给模型一份**目录**（约 150 token），模型自己 `recall` 取原文，只有 recall 才 `access_count+1`。矛盾 → `superseded` 不删可复活。规划：「回复余味」（用 AI 上一轮回复当下一轮检索 query）。

### 1.11 Aelios（wusaki0723/Aelios）

Cloudflare Workers 记忆网关。v2 宣传六层，v3-slim 已删 L1 digest。

- raw messages（14 天）→ `memories`（类型 fact/event/preference/relationship/boundary/habit/decision/note，带 `fact_key` 版本化 current|superseded|under_review）→ `precious`（珍贵原文，只增不删）→ world_fact + glossary → daily/weekly/monthly log
- 夜间 cron 抽取进 **candidates 人工审核**
- 召回三闸：precious 不进召回池（归冷启动包）；与核心层 Jaccard≥0.6 去重；30 分钟内注入过 ×0.5 降权防复读
- 自发浮现：importance≥0.75 且 7 天未被召回，每晚挑 2 条进 boot 包
- 有向关系图 2-hop：supports / contradicts / cause_effect / derived_from / same_thread / supersedes

### 1.12 WrenWen（ssxl0126/WrenWen）

公开仓库是**架构文档**不是可跑记忆引擎。记忆侧提到 2 层评分、防漂移；欲望内核见第 2 节。awesome 列表里的「约 2.4 万★ Letta」不要和它搞混。

### 1.13 Claude Code auto memory / autoDream

路径 `~/.claude/projects/<project>/memory/`：`MEMORY.md` 索引（每会话只加载前 200 行或 25KB）+ 按需 topic 文件。

`autoDream.ts` 门控：距上次 ≥24h → 期间会话 ≥5（排除当前）→ 文件锁 → fork 子 agent 跑 `/dream`。四阶段：Orient（ls + 读 MEMORY.md）→ Gather（grep 会话 JSONL）→ Consolidate（合并进已有 topic，相对日期转绝对，删被推翻事实）→ Prune and index（MEMORY.md &lt;200 行，每条一行 hook）。

**ASM 的 `memory/dream.py` 门控已经按这个抄过。**

---

## 2. 心情、驱力、主动开口

### 2.1 jiwen 积温（ClaraShafiq/jiwen）

约 500 行 JS，零依赖。**不管记忆，不管写回复**，只输出状态和触发。作者原话：角色不是在「想不想说话」，而是在「有没有被骰中」。

**五股感觉**

| 名字 | 范围 | 含义 |
| --- | --- | --- |
| connection | 0→1 | 想见你，沉默中累积 |
| pride | -1→+1 | 端着 / 放软 |
| valence | -1→+1 | 好受 / 难受（Russell） |
| arousal | -1→+1 | 焦躁兴奋 / 平静慵懒 |
| immersion | 0→1 | 手头有事做，面子缓冲 |

另有外部判定的 `userStatus`：active / busy / away / sleeping。

**漂移（每 5 分钟 `tick(minutes)`，不调模型）**

- `connection 增长 = baseRate × accelFactor × valenceFactor`。baseRate 看最后一句：晚安 0.0003/min，出门 0.0005，短消息 0.0010，默认 0.0007。过 `accelDelay` 后 `pow(1+c, connectionAccel)`。
- pride 回归 0（0.003/min）；被冷落升向 `prideDefendTarget`。
- valence / arousal 回归 0.005/min；connection 高时坏心情回归变慢（`valenceLockFactor`）；等待推高 arousal。
- immersion 0.01/min，约 60 分钟归零。

对话后轻量模型只返回 delta，例如 `{"pride":-0.1,"valence":+0.2,"arousal":-0.05,"connection":-0.15}`。强调用**旁观者**判，不要主模型自报。

**阈值**

- connection ≥0.20 → `observation`（心里注意到，不发出）
- ≥0.35 且 pride≥0.5 → `find_activity`（找事做，不开口）；pride&lt;0.5 → `contact`
- ≥0.50 强制 `contact`
- valence 过低或 arousal 过高 → `find_activity` 自我调节

**开口 ≠ 被回复**：开口只 `applyDelta({connection:-0.35})`；对方真回了才 `resetConnection()`。

数字经 `getPromptContext()` / `getStyleGuidance()` 译成人话。`tone-grid`：9 情绪簇 × 5 档 pride。可选 `getCircadianBias()`：深夜 arousal 设定点 −0.4，回归 ×1.5。带 `simulate.js` 跑事件线出 CSV 调参。

### 2.2 Drivesoid（A1batr055/Drivesoid）

HTTP sidecar，16 维 0–1：vitality, fatigue, longing, intimacy, possessiveness, lust, jealousy, anxiety, protectiveness, fear, contentment, elation, seeking, play, dejection, irritability。每维三层 `base`（快）→ `mood`（慢，12h）→ `neutral`（气质锚）。另有 frustration 0–3、pending、rejection_streak、sleep ∈ awake/asleep/interrupted。

- 每 2.5 min tick；base 以 tau 2–10h 指数衰减向 mood；睡眠时 mood 回归 ×3
- 习惯化：15 分钟内重复同标签 ×0.7ⁿ
- 时间累积：longing +0.04/h（上限 0.35）；6h 无互动 dejection +0.01/h；未回复 30m/1h/2h 里程碑加 anxiety
- 16 标签分类器 → `LABEL_DELTAS`（如 hostile: dejection+0.22, intimacy-0.22）
- 昼夜：每维独立高斯 peak（longing 22 点、elation 19 点、dejection 8 点）
- fatigue 由睡眠账本：目标 7.5h
- `display.lust>0.70` 每 4h 窗口 30% 生成 2h 过期「意图」
- `/api/drives/context` **直接把 0.xx 数字塞进 prompt**（多数项目认为这是反面教材）
- asleep 不回复；interrupted 迷糊短回

对 ASM：维度过多，生理/亲密向太重。可参考「三层快慢锚」和「未回复里程碑」，不要抄 16 维。

### 2.3 Eventide（chuli1122/Eventide）

NSFW 向生理状态。7 值 0–100：heat / pressure / control / sensitivity / reserve / possessiveness / fatigue。六相周期 stable → building → preheat → sensitive → ebb → recovery。18 类短时事件。静默 30/60/120 min 分档推高 pressure。梦境按周期概率掷骰，`after_effect_tags` 写回固定 delta。数值转 5 档中文，XML `<ephemeral_state>` 注入，不暴露数字。

### 2.4 Tidefall（Vael-KY/Tidefall）

Eventide 的 Supabase 移植。`pg_cron` 每 15 分钟 tick / 掷事件 / 快照。消息写入时扫触发词改 sensitivity/pressure/possessiveness。注意：`targets=0` 时函数跳过回落，数值只涨不落（实现坑）。

### 2.5 revive-companion（pearthink123/revive-companion）

**只做时机，不建模 AI 情绪。**

- 泊松：`P(hit)=1-e^(-λt)`，λ=0.15、t=0.5h → 约 7.2%；miss 后 +0.08，上限 0.95；发送后重置
- 贝叶斯用户 6 态：CHATTING / IDLE_ONLINE / BUSY / SLEEPING / AWAY / NEEDING；发送效用分别 0.2 / 0.7 / 0.1 / 0.0 / 0.3 / 0.9，阈值 0.5
- 信息增益：`gain=Σ(entropy×resolution)×0.85^连续发送次数`，`gain_ratio≥0.25` 且 `gain≥0.1` 才发
- quiet_hours 00–08 硬禁；午/深夜 30% 放行；`min_interval_hours=1`

扩展库 affective-longing 再叠 VAD 情绪 + 遗忘曲线记忆。

### 2.6 ai-companion-cot-emotion（yanke521/ai-companion-cot-emotion）

实践笔记（约 74KB README）。

- 16 个 drive；`分数 = min(CAP, 值+残留) − 基线`；tick 600s；向基线漂，anger 0.06 / 默认 0.02
- **自然生长故意不按「重启补时间」**，防重启轰炸
- 念头池 ≥0.80 升执念反哺 drive
- 只注入偏离基线 ≥0.05 的项；易变项挂**用户消息尾部**保 prompt cache（命中 68%→89%）
- 每条回复以 `[[思考：…]]` 开头，≥800 字意识流——**和 ASM 1 秒级语音冲突，不要抄这条**
- 工程教训：上线前要数各 drive 实际触发次数，否则会有维度永远隐身

### 2.7 WrenWen（ssxl0126/WrenWen）

文档 `docs/02-欲望驱动内核.md`。9 维 0..1：attachment / curiosity / expression / duty / roam / fatigue（gate，&gt;0.7 只拦不选）/ libido / stress / craft。偏移半衰期 8h；昼夜 cap 0.20，各维 peakHour（attachment 23、curiosity 11）。念头：闪念点 3 次→执念，喂 8 次出池。表达阈值 0.35、执行阈值 0.65、冷却 180 min。深夜固定做梦例程。唤醒锚定用户最后一条消息随机倒计时，不固定节拍。念头文本必须来自真实经历，不能现编。

### 2.8 Headlong（laude-institute/headlong）

Bash 微 harness，无情绪数值。持续内心独白：thought / action / observation / idle / message。空闲思考指数退避，cap 60s / 300s。入站消息永远 fast-reply。`share` 有新发现才发，24h 内拒绝重复。可输出 `NO_REPLY`。整个系统就是 inner monologue，人类消息只是流中一条 observation。

对 ASM：可参考「没事时后台想一想」，但不要做成回复前必跑的长 CoT。

### 2.9 Aikeya（aikeyaorg/aikeya）

开源 Grok Companion 味。affection 0–1000，trust/intimacy/comfort/respect 0–100，energy 0–100，mood 12 种。8 阶段 stranger→soulmate，门槛表示范：Dating 要 affection 600 + trust 85 + intimacy 50 + 14 天 + 事件 `confession_accepted`。启发式加减 + ±20% 随机；离线 ≥48h affection 降，≥3 天 mood→melancholy。LLM 可输出 JSON delta，被夹在启发式 ±2 倍（energy 不可改）。**游戏养成感重，和「像人」方向相反。**

### 2.10 astrbot_plugin_private_companion（menglimi/astrbot_plugin_private_companion）

文档层（未深挖源码数值）。每日精力/情绪/睡眠/健康/饥饿；好感 8 阶段 + 迟滞 + 只向 0 回落；越界分轻中重。主动消息是候选生命周期：生活事件 → 时间窗与价值评分 → 免打扰/休息/繁忙/未回应边界 → 人格判断 → 复核 → 发送 → 审计。额度取全局/用户/阶段/状态的最小值。五层 prompt，稳定前置打 cache。

### 2.11 astrbot_plugin_proactive_chat（DBJD-CR/astrbot_plugin_proactive_chat）

沉默后在 30–900 分钟随机调度；`max_unanswered_times=4` 后停。用**模拟用户消息**注入，带 `{{unanswered_count}}`，让语气带失落。quiet_hours 默认 1–7 点。这是 ASM 现在 30% 骰子的同类，更完整一点（未回复升级 + DND），仍是随机间隔。

### 2.12 Aura（gqy20/Aura）

Android。`EmotionStateMachineImpl.kt`：mood 字符串 + intensity 0–1 + 最近 20 条历史。关系单一 `currentLevel` 0–1。**无自动漂移**，每轮 OutputParser 写入。注入最近 5 条情绪链和关系等级文字。PulseWorker 主动推送标了未实现。Dream Loop 默认 6h 本地 Qwen 做模式识别（第三方观察者，不是回复前 CoT）。

### 2.13 yoji（wangxijie001/yoji）

8 种激素 0–100（多巴胺、血清素、GABA、内啡肽、皮质醇、肾上腺素、催产素、褪黑素），各有基线。每 5 min：`newLevel = level + (baseline - level)·0.02`。褪黑素走时钟（夜 70–90，昼 10–30）。LLM 按步长表改激素；示例「距上次 5 天：多巴胺−4×5…」。注入用 5 档中文，**禁止说「我多巴胺很高」**。主动开口间隔 10→20→40… 翻倍到 12h，用户说话重置。晚 9 点 Live2D 换睡衣。

对 ASM：激素叙事好玩，但和积温的「想见你/嘴硬」相比更难调、更难解释。若要昼夜，优先抄褪黑素式一条偏置，不要上 8 激素。

### 2.14 ears（eveacla11/ears）

用户侧声学，不是 AI 自身状态。9 特征相对本人 200 条历史的 median±MAD，z 阈值 0.8 / 1.5 / 3。LLM 结合「她说的话 + 和平时比」选 1 个标签。建议绑到**这一句**，不要全局漂浮注入（实测会乱）。ASM 以后若做「你今天比平时小声」，可以挂在 ASR 后当情境，不进 self_state 轴。

---

## 3. 跨项目共性

### 记忆

几乎家家都有：

- 热/冷分层注入：常驻小包 + 按需检索（Elino facts、VAPE in_context、Aelios boot、Paramecium L2+目录、Letta blocks、Claude Code MEMORY.md）
- 艾宾浩斯式衰减 + 「被想起」延寿（Elino / Ombre / kiwi / 星图）。kiwi 和 Paramecium 区分「进过目录」和「真正被召回」
- 情绪加权遗忘：Elino 用 |valence−0.5|，Ombre 用 arousal，kiwi 用 emotional_weight；Ombre 与星图都是 ≤3 天看新鲜度、&gt;3 天看情绪
- 睡眠/梦境整合：VAPE、kiwi、Aelios、Letta、Claude Code。共同动作：去重、合并、矛盾修正、写日志
- 矛盾 = supersede 不删（kiwi valid_until、Paramecium superseded、Aelios fact_key、Soul-of-Waifu healing_log）
- 钉选永不衰减
- 前瞻记忆：Elino promises/openLoop、Meux threads、kiwi Foresight、星图 schedule、VAPE prospective intentions
- 日历层级压缩：kiwi 日→年、Aelios daily/weekly/monthly、VAPE temporal selves

较独特：Ombre 涟漪与 feel 结晶；kiwi soften；星图引用权限三档；Meux 硬护栏；VAPE affect gate + 人设提案制；Paramecium 原文为唯一真相；Aelios 召回降权防复读。

### 心情与开口

几乎家家都有：

- 连续值向基线衰减（积温、Drivesoid、cot-emotion、WrenWen、yoji、Eventide、Aikeya 离线）
- 沉默推高想念/焦虑（积温 connection、Drivesoid longing、Eventide pressure 分档、cot-emotion 沉默四切、proactive_chat unanswered_count）
- 阈值触发优于纯骰子（积温 0.20/0.35/0.50、WrenWen 0.35/0.65、cot-emotion 三档坡）
- 概率时机 + 冷却仍常见（revive 泊松、yoji 翻倍间隔、proactive_chat 30–900min）——体感更「人机」，积温和 WrenWen 都改成锚定用户最后一句
- 昼夜偏置（Drivesoid 每维 peak、yoji 褪黑素、积温 circadian、WrenWen peakHour）
- DND / 睡眠闸门（revive 00–08、proactive_chat 1–7、Drivesoid asleep 不回）
- 未回复升级再停（proactive_chat 最多 4 次、Drivesoid rejection_streak、revive 信息增益 0.85ⁿ）
- **数字译成人话再给模型**（积温 tone-grid、Eventide 五档、yoji 区间表）。Drivesoid 直接给 0.xx 是反例；cot-emotion 自己反思「不该让模型看数字」
- 易变状态挂消息尾 / ephemeral 块，稳定人设在前，保 prompt cache
- 旁观小模型判情绪，主模型不自报（积温、Drivesoid 分类器、yoji、ears、Aikeya delta 夹紧）

**开口 ≠ 被回复**：积温开口只减 connection；Drivesoid 意图 2h 过期；cot-emotion 区分 `analyze_incoming` / `analyze_reply`。

**工程坑（多家独立踩到）**

1. 时间补偿按「过了多久」不是「跑了几次」；但「自然生长」故意不补，防重启轰炸
2. 「某维从未触发」不报错——上线前数触发次数
3. 固定节拍主动消息非常人机
4. 回复前 800 字 CoT 和实时语音不兼容

---

## 4. 对 ASM 的可抄清单

### 记忆（你自己搞；此处只列映射）

现有：`MEMORY.md` 索引、`relationship.md`、`self_state.md`、`user/*.md`、`logs/YYYY-MM-DD.md`、dream 24h+5 会话+锁、recall 短工具循环、observe 只 append。缺口：extract 几乎不过滤，log 被「你好」和 `session_open` 污染；前瞻混在 relationship 里；self_state 不会漂移。

可直接搬进文件+grep、不必上向量的：

| 机制 | 抄谁 | 落到哪 |
| --- | --- | --- |
| 写触发（不记寒暄/系统轮/自己的话） | Warashi | `memory/prompts/extract.md` |
| 语义 / 情景 / 前瞻拆开 | Meux threads、Elino promises、Soul-of-Waifu USER | `user/*.md` / `logs/` / 建议 `threads.md` |
| 热度字段 + dream 里算衰减 | Ombre 公式、kiwi 分档 | log 行尾元数据；dream 重写 `MEMORY.md` |
| 只有进 prompt 才算召回 | kiwi、Paramecium | observe/recall 计数 |
| 引用权限三档 | 星图 | `recall.md` |
| 巩固三步：整理 / 升成语义 / 前瞻 | kiwi Dream、VAPE forward viability、Claude Code autoDream | `dream.md`（门控已有） |
| 人设只读、dream 只能提案 | VAPE gate | 保持 `prompts/01-soul.md` 只读 |
| 常驻块 cap | Warashi 1500 | `MEMORY.md` / relationship / self_state 上限 |
| 矛盾 supersede 不删 | 多家 | changelog + archive |
| 心情同调召回 | Ombre valence 偏移 | recall 提示优先取与当前心情相近的片段 |

### 心情与开口（ASM 现在最值得做的）

接到现成 [`ImpulseScheduler`](../../backend/asm/impulse/scheduler.py) 的 idle timer，把 [`idle_companion` 的 0.3 骰子](../../backend/asm/impulse/triggers.py) 换掉。不改 Orchestrator 接口，仍发 `ProactiveTrigger(reason, hint)`。

推荐形态（积温）要点：

1. 后台几股连续感觉，纯数学 tick，实时路径零模型
2. 到阈值才开口；想开口但拉不下脸可以先不说
3. hint 是人话，对话模型不看数字
4. 开口只减「想见你」，对方真回了才清零
5. 轮末用旁观小模型给 delta，不要让阿澄自己报心情
6. 保留 session_open、到期回访、每日上限、冷却；免打扰和昼夜偏置可后加

厚薄三档（尚未拍板）：

- 薄：想见你 + 心情好坏/烦不烦（connection / valence / arousal）
- 中：再加拉不下脸（pride），可选 immersion 当「找借口去做点事」
- 中 + 护栏：再加 Meux「不许瞬间原谅」——负面高强度时不能下一轮变开心

不把 30% 随机和阈值叠在一起。参数用事件线模拟再调，不靠猜。

`session_open` 与到期回访先留：一个是见面礼，一个是记事本；内部心情管「没事会不会找你」。

---

## 5. 明确不抄

- 向量库 / BM25 作为记忆主检索（已否决；grep 是检索）
- Aikeya 式好感升级打怪
- Eventide / Tidefall 身体周期（NSFW、和一对一语音陪伴目标不符）
- Drivesoid 16 维 sidecar、cot-emotion / WrenWen 9–16 维欲望（第一版调不完）
- 回复前 ≥800 字内心独白（打实时延迟预算）
- 主对话模型每轮重写整份 core_memory（Warashi 单文件适合小 cap；ASM 已分主题，dream 合并即可）
- 让对话模型直接 `write_section` 主题文件（保持 observe 只 append）
- 固定 cron 节拍主动消息当主策略
- 把数字原样塞进对话 prompt（Drivesoid 反例）

---

## 仓库速查

| 项目 | 仓库 |
| --- | --- |
| awesome-ai-companion | https://github.com/DasterProkio/awesome-ai-companion |
| Project-elino | https://github.com/Tacky7788/Project-elino |
| MeuxCompanion | https://github.com/meet447/MeuxCompanion |
| Warashi | https://github.com/inni918/warashi |
| VAPE | https://github.com/syahiidkamil/vibe-ai-partner-entity |
| Ombre-Brain | https://github.com/P0luz/Ombre-Brain |
| kiwi-mem | https://github.com/LucieEveille/kiwi-mem |
| Memory Constellations | https://github.com/ClaraShafiq/MemoryConstellations |
| Soul-of-Waifu | https://github.com/jofizcd/Soul-of-Waifu |
| Letta | https://github.com/letta-ai/letta |
| Paramecium | https://github.com/Shitsuten/paramecium |
| Aelios | https://github.com/wusaki0723/Aelios |
| WrenWen | https://github.com/ssxl0126/WrenWen |
| jiwen | https://github.com/ClaraShafiq/jiwen |
| Drivesoid | https://github.com/A1batr055/Drivesoid |
| Eventide | https://github.com/chuli1122/Eventide |
| Tidefall | https://github.com/Vael-KY/Tidefall |
| revive-companion | https://github.com/pearthink123/revive-companion |
| ai-companion-cot-emotion | https://github.com/yanke521/ai-companion-cot-emotion |
| Headlong | https://github.com/laude-institute/headlong |
| Aikeya | https://github.com/aikeyaorg/aikeya |
| astrbot private companion | https://github.com/menglimi/astrbot_plugin_private_companion |
| astrbot proactive chat | https://github.com/DBJD-CR/astrbot_plugin_proactive_chat |
| Aura | https://github.com/gqy20/Aura |
| yoji | https://github.com/wangxijie001/yoji |
| ears | https://github.com/eveacla11/ears |
