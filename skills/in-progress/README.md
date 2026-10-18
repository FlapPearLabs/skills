# In Progress

Beta. These skills are public on purpose — try them and tell me what breaks. They're excluded from the plugin and the top-level README until they graduate to a stable bucket, they get no docs pages, and they can change or disappear without warning.

The plugin won't give you these. Install one directly:

```bash
npx skills@latest add mattpocock/skills --skill=<name>
```

- **[loop-me](./loop-me/SKILL.md)** — Grill yourself into implementable workflow specs over multiple sessions, using the current directory as a stateful workspace. User-invoked.
- **[annotate-video-language](./annotate-video-language/SKILL.md)** — 镜头与剪辑标注助手：拆解景别、运镜、剪切、转场和衔接，生成中文标注视频、AI 生成描述与真实素材剪辑指令。模型或用户可调用；需要 Python、Pillow、ffmpeg 和 ffprobe，本机播放器自动打开仍需在目标设备验证。
- **[writing-beats](./writing-beats/SKILL.md)** — Shape an article as a journey of beats, choose-your-own-adventure style. Pick a starting beat, write only that beat, then pivot to the next, until the article reaches a natural end.
- **[writing-fragments](./writing-fragments/SKILL.md)** — Grilling session that mines you for fragments — heterogeneous nuggets of writing — and appends them to a single document as raw material for a future article.
- **[writing-shape](./writing-shape/SKILL.md)** — Take a markdown file of raw material and shape it into an article paragraph by paragraph, arguing format choices at each step.
- **[claude-handoff](./claude-handoff/SKILL.md)** — Hand the current conversation off to a fresh background agent that picks up the work immediately, seeded with a handoff summary via `claude --bg`. User-invoked.
- **[setup-ts-deep-modules](./setup-ts-deep-modules/SKILL.md)** — Wire dependency-cruiser into a TypeScript repo so each package is a deep module — implementation hidden in subfolders, reachable only through its entry-point files, tests exercising it through those. User-invoked.
