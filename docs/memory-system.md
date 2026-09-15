# 记忆系统

日期：2026-09-15  
状态：v1 已实现。对照 [context-compression.md](context-compression.md)。

## 产品

这是一段持续陪伴，不是 ChatGPT 那种多会话。用户每次打开就是打招呼接着聊。没有会话列表，没有「新对话」。记忆过程不对用户暴露。

代码里的 `Session`、WebSocket 连接、进程寿命只是插头。人走开不是「这段对话结束」。进程还在时，不要因为断线清空窗口。

阿澄（对话模型）不碰文件。她只读后台放进 prompt 的工作集。

## 和压缩的边界

| | 记忆 | 压缩 |
|---|---|---|
| 目的 | 下次还认识他 | 1M 窗口满了还能接着聊 |
| 时间跨度 | 跨天、跨打开 | 当前还有效的脉络 |
| 默认 | 闲聊不写档案 | 闲聊摘要为「无」 |
| 失败 | 乱记、把陪聊写成日记 | 从闲聊编造任务/议题 |

两套共用「闲聊默认不值」的判定，但记忆只收**稳定下来**的；压缩只收**现在还有效**的相处增量。压缩不写 `MEMORY.md` / `logs/`。记忆不负责裁 `Session.messages`。

小名、稳定称呼进 `relationship.md`，不写进 `persona.md` / Soul。压缩摘要在记忆还没接住前必须仍能带着互称，见 [context-compression.md](context-compression.md)。

## 值得记下什么

陪伴的底色是陪着，常常没有任务、没有目标。不能按 coding agent 的待办来抽。判据：

**忘掉会伤到他，或她会像没共同经历过 —— 才写。过场丢掉。拿不准则不写。**

写：

- 纠偏与边界：怎么称呼、什么不能再提、哪句过分了。尽量留他的原话。
- 稳定偏好与身分：工作、家人、口味、希望被怎样对待。偶尔一次的口味不算稳定。
- 夹在闲聊里的自我揭露：例如「其实最近睡得不好」。
- 约定，以及他明确说以后再说的线。
- 已经稳定的两人称呼或梗。开一次的玩笑不记。

不写：

- 寒暄、嗯嗯、天气、过场式的吃什么。
- 没有新信息的陪聊。
- 她自己的话和长独白（Warashi：不记 AI 自己说的话）。
- 系统轮、见面打招呼。现有流水已被这类污染，extract 必须停掉。
- 一次性琐事、已被他纠正过的旧说法（新覆盖旧，旧的不要并存）。

没有值得写的，就是空操作。空操作是正确结果。

## 两层

档案只给记忆 LLM：

```
data/memory/
  persona.md          只读。她是谁，只有人改。
  user/*.md           关于他的主题档案
  relationship.md     关系、约定、梗、未完的线
  self_state.md       她的心情与心事，有上限
  logs/YYYY-MM-DD.md  每日流水，只追加
  transcripts/*.jsonl 逐轮原文，崩溃可回放
  rolling.md          压缩文档里的滚动摘要，记忆 agent 不维护
```

工作集只给阿澄：一份 `MEMORY.md`。后台把档案里这轮用得着的东西晋升进来，过时的撤下。她没有 `ls/read/grep`。不要把主题文件或 snippets 另开通道塞进她的 prompt。

`persona.md` 记忆 LLM 不能写。`MEMORY.md` 约 200 行 / 25KB 硬帽，超了必须先删再写。

## 阿澄怎么读

`prompts/01-soul.md` / `02-medium.md` / `03-tools.md` 是稳定系统前缀，不要把 MEMORY.md 拼进去。

第二块 system：`长期记忆：` + 当前 `MEMORY.md`。本轮开口用上一轮缓存的正文，不等 recall。recall 若改了文件，下一轮才换。

## 时机

| 何时 | 做什么 | 是否调记忆 LLM |
|---|---|---|
| 每轮结束 | 只把原文 append 进 transcripts | 否 |
| 人离开（WS 断开） | extract：扫这段时间的 transcript，值得的才 append 进今天的 log | 是，同一次离开最多一次 |
| 他开口 | recall：档案里当前窗口没有的，晋升进 MEMORY.md | 是，异步，有 deadline，不挡开口 |
| 门控后台 | dream：logs 合并进主题文件，修剪 MEMORY.md | 是 |

人离开才 extract，因为窗口里的原文对话模型已经看见了；再每轮抽一次解决不了「上下文里已有」的问题。寒暄、过短、没有用户文本，离开也不抽。

recall：寒暄跳过；同一句不跑第二次；partial 和提交合并成一次。超时用缓存的 MEMORY.md。

dream 仍用现有门（间隔、次数、锁）。相对日期转绝对，矛盾覆盖，重写 MEMORY.md 钩子。

## 实现

独立于阿澄的 Memory LLM（默认同模型、另一路 client）：非流式 tools。extract / recall 关 thinking；dream 可开。阿澄只注入 `MEMORY.md`。TurnClosed 只写 transcripts，不跑 extract。

程序侧：`MemorySupervisor` 独占 `ls/read/grep/write/write_section/append`。`persona.md` 只读。`MEMORY.md` 超 200 行或 25KB 时拒绝写入，必须先删。无 API key 时不抽 log（避免寒暄污染），压缩走启发式摘要。
