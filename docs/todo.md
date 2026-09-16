# 待做

日期：2026-09-16  
状态：清单。对照 [memory-system.md](memory-system.md)、[context-compression.md](context-compression.md)、[开源陪伴调研](2026-09-14-open-source-companion-research.md)、[harness 设计](superpowers/specs/2026-09-15-memory-agent-harness-design.md)。

下面按主题，不按实现顺序。动手下一件之前先回来勾范围。

---

## 1. 记忆 agent 的 harness — 已落地

设计与代码都齐：[memory-agent-harness-design.md](superpowers/specs/2026-09-15-memory-agent-harness-design.md)。

已有：

- 开口不跑记忆 LLM。人离开且有新轮次才巩固一次 ReAct。
- 类型文件：`user.md` / `relationship.md` / `boundaries.md` / `threads.md`，外加 `MEMORY.md`。
- 工具：`search_turns` + `ls/read/grep/write/write_section`。没改类型文件不许写小抄。
- 空操作也推进 `last_run`。无 API key 不启动、不推进游标。
- 情感不在这里做。`self_state.md` 记忆 agent 不碰。

还剩（实聊，不是再改循环）：

- 巩固是否真把互称、边界、未完的线写进对的类型文件。
- 小抄是否短、是否把档案全文倒进去。
- `consolidate.md` / `agent.md` 按实聊再收。

不要在循环上再叠热度、遗忘、向量。

---

## 2. 语音系统改造

现状：听是本地 ASR（sherpa），说是火山 TTS，编排里有投机、打断、echo holdoff。缺密钥或模型时是 mock / 蜂鸣。

待定，还没写改造方案：

- 首包延迟、断句与口型对齐是否够用。
- 打断后的残留 ASR、假打断、她说话时麦怎么收。
- mock 与真链路的行为是否一致，方便无密钥开发。
- 要不要换 TTS/ASR，或加流式更高的一路。

未开设计文档之前不要改协议。

---

## 3. 上下文压缩：关键内容真的留下了吗

v1：预留 15% 窗口，隐式压缩，五段模版，异步一次无工具 LLM，写入 `rolling.md`。阿澄只看见「近期脉络」，用户不可见。

未验证、未加固：

- 真到 ~85 万 token 时，互称、纠偏、未散的口气、短线约定、接话短事实是否还在。
- 闲聊是否被编成「议题」。
- 被裁原文在 `turns.sqlite`，巩固用 `search_turns` 再扫。
- 打断路径不调度 compact，下一轮 StartTurn 才硬裁。
- `_compacting` 在 SummaryReady 丢失时会卡住。
- token 估计仍是 `len//2`。

---

## 4. 缓存机制

两层都薄，效果没测：

- **工作集缓存**：开口用磁盘上的 `MEMORY.md`；巩固在人离开后才可能改小抄，改完若人已回来再发 `ContextReady`。
- **前缀缓存**：Soul / medium / tools 是稳定第一块 system，有利于服务商 prefix cache。`长期记忆` 和 `近期脉络` 一变，后面整段 cache 作废。巩固变少之后，小抄不应每轮都换。

待做：测 DeepSeek 是否命中前缀缓存；稳定块尽量不动；工作集更新别误伤 Soul。不要和浏览器 HTTP cache 混为一谈。

---

## 5. 分层提示词优先级

口头约定过，代码只是拼接顺序，没有冲突仲裁：

```
Soul（01-soul.md）     最高。聊天不改。她叫阿澄。
记忆（MEMORY.md）      稳定的他、你们、小名。
滚动摘要 + 近期原文    这段还有效的增量。
情境                   现在几点、距上次多久。
```

待写进 prompt 和测试：外号不能改 Soul 里的名字；记忆与 Soul 冲突听 Soul；摘要与记忆冲突听记忆（摘要只补记忆还没接住的）；阿澄不可见工具/压缩/抽记忆过程。

---

## 6. 提示词书写

现有：`soumate/prompts/01-soul.md`、`02-medium.md`、`03-tools.md` 给阿澄；`memory_agent/prompts/` 里 compress / consolidate / agent 给后台。后台类型路由已经写进巩固提示词。

待做：

- 阿澄三件套写成人话、短、可测（一次一两句、标记、不要对用户提起系统）。
- 后台检索提示按实聊再收：何时 `search_turns`、空结果怎么办、分页。
- 不要把档案全文倒进工作集（巩固提示词已写，实聊核对）。

---

## 7. 情感系统

现状：句末 `⟦emotion⟧` / `⟦motion⟧`，embodiment 规则映射到 Live2D。`self_state.md` 记忆 agent 不维护。impulse 是随机骰子 + 距上次 / 未完话题扫描。

待设计（先文档后代码）：

- 心情要不要有内部状态（好坏、烦不烦），谁写、谁衰减。
- 标记词汇表是否够，和脸是否一对上。
- 主动开口要不要跟心情 / `threads.md`，而不是纯随机。
- 不把量表念给用户听。

调研里别人的 valence 公式可参考，不默认照抄进产品。

---

## 8. 记忆系统优化（类脑）

v1 是「值得才写、空操作正确」。没有热度、没有遗忘曲线、没有「用过才算想起」。

以后才考虑，且要能说明为什么陪伴需要它：

- 稳定事实（互称、边界）不该按曲线忘掉。
- 若做衰减：只对工作集 / 类型档案里的软事实，巩固里算，不要每轮算。
- 进阿澄 prompt 才算召回（kiwi / Paramecium 那套），不要因为 grep 到了就加分。
- 调研见 [开源陪伴调研](2026-09-14-open-source-companion-research.md) 遗忘与热度表。未设计前不要加公式。

---

## 刻意不做

- 多会话列表、新对话按钮。
- 把对话库灌进阿澄的 1M 窗口。
- 给阿澄文件工具或 `search_turns`。
- 用向量库替换文件档案。
- 聊天改 Soul。
- 嵌 Pi / 给后台 bash。
