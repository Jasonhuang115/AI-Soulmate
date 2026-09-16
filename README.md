# ASM

本机单用户、长期一对一的陪伴 harness。她叫阿澄。浏览器只负责麦、播放、脸和聊天；对话、记忆、听和说都在本机一个 Python 进程里，模块只通过事件总线通信。

没有会话列表，没有「新对话」。人设在 `soumate/prompts/`，聊天不改。关系和档案在 `data/memory/`。

```
soumate/             阿澄
  asm/               编排、听、说、LLM、主动开口、WebSocket
  embodiment/        逻辑表情 / 动作 → 发给前端的指令
  prompts/           Soul / medium / tools，聊天不改
memory_agent/        后台记忆 LLM（人离开才跑）
  agent.py           总线 + 巩固 ReAct
  types.py
  prompts/           agent / consolidate / compress
  store/             sqlite、类型文件工具、巩固锁
frontend/            浏览器：VRM、聊天、麦、播放
data/memory/         运行时档案（sqlite + 类型文件），不是代码
test/
scripts/             一次性准备：ASR 模型、VRM 样例与手势
```

### 怎么跑

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd frontend && npm install && cd ..
bash scripts/fetch_vrm_assets.sh
cp .env.example .env
```

`.env` 里填 `DEEPSEEK_API_KEY` 和火山 TTS 密钥才会走真模型和真语音。没密钥时是 mock 脑和蜂鸣 TTS。

```bash
# terminal 1
source .venv/bin/activate
PYTHONPATH=soumate:. uvicorn asm.app:app --reload --port 8765

# terminal 2
cd frontend && npm run dev
```

打开 Vite 地址（默认 http://localhost:5173/）。听还要本地 ASR，见下面语音一节。测试：`python -m pytest -q`；有密钥时加 `--integration`。

约定：对话模型关 thinking（`extra_body={"thinking": {"type": "disabled"}}`）；开口不跑后台记忆 LLM；VRM / VRMA 二进制和 ASR 模型不要提交。

---

## 几个部分

### 前台 VRM 形象控制

阿澄在台词里不写「我笑了」，只在句末带标记：`⟦happy⟧`、`⟦wave⟧` 这类。词汇表来自 `frontend/public/gestures/catalog.json`（`soumate/embodiment/vocab.py` 读取）。`embodiment` 收到标记后按规则收成一条 `AvatarCommand`（expression / motion / 是否立刻切），经 WebSocket 发给浏览器。

前端是 Three.js + `@pixiv/three-vrm`：脸用 VRM 预设表情，身体播共享 `.vrma`。表情和动作都跟那一句 TTS 对齐。嘴型走正在播的 PCM 能量。安静时眨眼、看镜头。把另一个 `.vrm` 拖到画布上即可换人，动作库不用重做。

默认样例人和动作库不进 git：

```bash
bash scripts/fetch_vrm_assets.sh          # 样例人 + 阶段1 约 12 条
bash scripts/fetch_motion_packs.sh        # Motifect 日常/表情/位移包（BVH）
bash scripts/convert_mixamo_to_vrma.sh    # 转成 catalog 里的 .vrma
```

第一段会下载样例 `.vrm`（优先 ChatVRM `AvatarSample_B`，被拦时用 three-vrm 官方例模）和约 12 条现成 VRMA（挥手、鼓掌、思考等）。后两段把 Motifect 包转成 catalog 里剩下的约 88 条。`?model=other` 加载 `frontend/public/models/vrm/other.vrm`；`?faceDebug=1` 用键盘试表情和动作。

播放器按 `catalog.json` 播。本机 `prompt_phase` 已是 3：磁盘上约 100 条 VRMA，提示词只注入约 50 个分组标签，不会把文件名全塞给模型。也可以把 Mixamo FBX 按逻辑名放进 `data/mixamo/`（如 `nod.fbx`），同一转换脚本会顺带处理。`.vrm` / `.vrma` 已 gitignore。许可见 `frontend/public/gestures/NOTICE.txt`。转换结果只给本机用，不要当原作再分发。

### 语音系统

听和说是两截，缺一截页面上就像「没有语音」。

- **说**：火山 TTS。打字发送就会出声。第一次要点一下页面，浏览器才允许播。没密钥时是蜂鸣。
- **听**：本地 sherpa ASR + Silero VAD。没装时「开麦」空转，顶栏显示「听关」。

```bash
pip install -e ".[asr]"
bash scripts/download_asr_models.sh
```

模型在 `data/models/`（已 gitignore）。装完重启后端。`GET /health` 里 `listen=sherpa`、`speak=volc` 才算两端都通。

编排里有投机开口、打断、她说话时丢掉残留 ASR、假打断后的 echo holdoff。开麦后说话会自动识别；她在说时可以打断；只说「嗯」不会取消她。

### 后台记忆系统

和前台阿澄是两路。记忆过程不对用户暴露。开口只用磁盘上现成的 `MEMORY.md`，不等后台。

人离开且库里有新轮次，才跑一场巩固（ReAct）。程序只跳过「零条新轮次」；寒暄值不值得写，由模型判断。无 API key 不启动。

后台维护两套：

1. `data/memory/turns.sqlite` — 对话收据。程序每轮 append。模型只能 `search_turns`，不能写库。
2. 类型文件 — `user.md`（他）、`relationship.md`（你们）、`boundaries.md`（纠偏）、`threads.md`（约定和未完的线）。巩固时才重写给阿澄看的 `MEMORY.md`。

阿澄不读库、不读四类档案、没有文件工具。压缩（窗口满了写 `rolling.md`）不是记忆，见 [context-compression.md](docs/context-compression.md)。情感不在这里做，`self_state.md` 记忆 agent 不碰。细节：[memory-system.md](docs/memory-system.md)、[harness 设计](docs/superpowers/specs/2026-09-15-memory-agent-harness-design.md)。

### 前端表现

`frontend/` 是 Vite + 原生 TypeScript，哑终端。WebSocket 收发控制面 JSON；上行音频是 PCM 二进制帧。页面上就是：VRM 全视口舞台、聊天记录、输入框、开麦。打开页面会先打招呼（知道隔了多久）；麦开着且安静一会儿，她可能主动开口。前端不跑模型、不读记忆文件。

### Agent 本身的构造

一个进程，一条 `EventBus`。`Orchestrator` 只管对话状态机（听 / 投机 / 想 / 说）和打断计时，不写 prompt、不写档案。挂在总线上的是：

- **Brain**：DeepSeek（没密钥则 mock）。系统提示词三件套：`01-soul.md` 人设、`02-medium.md` 说话规矩、`03-tools.md` 句末标记。上面再叠 `MEMORY.md`、可能出现的滚动摘要、现在几点。
- **Voice / Perception**：TTS 与 ASR，只发音频和转写事件。
- **Embodiment**：标记 → 脸和手势。
- **MemoryAgent**：每轮只 append 库；人离开才跑巩固 ReAct。
- **Impulse**：闲时可能主动开口。

实时路径不 await 记忆写入。阿澄看不见工具循环、压缩、抽记忆的过程。

---

## 待完成

完整清单在 [docs/todo.md](docs/todo.md)。动手下一件之前先回去勾范围。当前大块：

- **记忆抽取质量** — 循环已落地。还要看实聊：互称、边界、未完的线有没有写进对的文件；小抄是否短、有没有把档案全文倒进去。不要再叠热度、遗忘、向量。
- **语音** — 还没写改造方案。首包延迟、口型对齐、假打断、换引擎，都先出设计再动协议。
- **压缩** — v1 有了，没在长窗口上验证互称和纠偏是否还在；token 估计仍是 `len//2`；`_compacting` 在摘要丢失时会卡住。
- **缓存** — Soul 那块稳定、有利于前缀缓存；小抄一变后面整段作废。DeepSeek 是否命中还没测。
- **提示词** — 分层优先级（Soul > 记忆 > 摘要）还只是拼接顺序，没写进 prompt 和测试。阿澄三件套和巩固提示都要按实聊再收。
- **情感** — 现在只有句末标记映射到脸。心情内部状态、主动开口跟不跟 `threads.md`，先设计后代码。
- **类脑记忆** — 以后才考虑，且要能说明陪伴为什么需要它。

刻意不做：多会话列表、把对话库灌进阿澄窗口、给阿澄文件工具、用向量库换掉文件档案、聊天改 Soul、嵌 Pi / 给后台 bash。
