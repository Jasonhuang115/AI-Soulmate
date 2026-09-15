# ASM

本机单用户的长期一对一陪伴 harness：Python asyncio 后端 + Vite 原生 TypeScript 前端。模块只通过事件总线通信。

浏览器只负责麦、播放、脸和聊天。对话状态机、语音和主动开口在 `backend/`，长期记忆在 `memory/`，表情与 companion tool 在 `embodiment/`。人设、说话介质和情感标记在 `prompts/`。

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cd frontend && npm install && cd ..
cp .env.example .env
```

填 `.env` 里的 `DEEPSEEK_API_KEY` 和火山 TTS 密钥后才会走真模型与真语音。没密钥时用 mock 脑和蜂鸣 TTS。

语音是两截，缺一截页面上看起来就像「没有语音」：

- **说**：打字发送就会 TTS 出声。第一次要点一下页面，浏览器才允许播。
- **听**：还要装本地 ASR。没装时「开麦」是空转，页面顶栏会显示「听关」。

### 听（本地 ASR / VAD）

```bash
pip install -e ".[asr]"
bash scripts/download_asr_models.sh
```

模型落在 `data/models/`（已 gitignore）。装完后**重启后端**。`GET /health` 里 `listen` 变成 `sherpa`、`speak` 变成 `volc` 才算两端都通。

### 脸（Live2D）

默认是 Live2D 官方样例 **Epsilon**（粉双马尾）。说话嘴动，情绪跟那一句开播对齐。

授权清楚、真正白毛的官方免费样例目前只有 **Kei**（短白发）。官网下载要勾使用条件，没法直接镜像进仓库：

1. 打开 https://www.live2d.com/learn/sample/kei/ 下载 runtime。
2. 把 `*.model3.json` / `*.moc3` / 贴图解压到 `frontend/public/models/kei/`。
3. 刷新页面，会优先加载 Kei。

换模型：新开一个目录，放 `avatar_map.json`（逻辑表情/动作 → 模型 expression / motion）。

Epsilon / Kei 都受 Live2D Free Material License 约束，不是 ASM 自己的许可证。

## Run tests

测试都在仓库根目录的 `test/`。

```bash
python -m pytest -q
```

有密钥时：

```bash
python -m pytest -q --integration
```

## Run locally

```bash
# terminal 1
source .venv/bin/activate
PYTHONPATH=backend:. uvicorn asm.app:app --reload --port 8765

# terminal 2
cd frontend && npm run dev
```

打开 Vite 地址（默认 http://localhost:5173/）。

- 打字发送：文字进、语音出、再说一句会打断。
- 开麦：说话自动识别；她在说时你可以打断；只说「嗯」不会取消她。
- 打开页面会先打招呼（知道隔了多久）；麦开着且安静一会儿，她可能主动开口。
- 人设在 `prompts/01-soul.md`，说话规矩在 `02-medium.md`，句末情绪标记（`⟦happy⟧`）在 `03-tools.md`。关系和心情在 `data/memory/`。

## 约定

- 对话模型必须关 thinking：`extra_body={"thinking": {"type": "disabled"}}`。
- 实时路径不 await 记忆写入；recall 有 deadline。
- Cubism 核心和 ASR 模型不要提交。
