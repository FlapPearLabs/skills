# 运行与 Workbuddy

WorkBuddy 官方文档提供的本地入口是：专家·技能·连接器 → 技能 → 添加技能 → 上传技能。把完整 annotate-video-language 目录作为本地技能包导入，保留 scripts、references、assets、agents。该入口来自官方文档，当前用户电脑上的实际安装状态仍需实测。不要猜目录，不把 Codex 目录冒充 WorkBuddy 目录。

本地导入说明：https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market

本技能采用通用 name/description 元数据。若另行发布到 WorkBuddy 开放平台，按 https://open.workbuddy.cn/docs/skill 为发布副本补充 description_zh、description_en、version、author 等平台必填元数据；不要把开放平台发布与本地安装视为同一个已验证流程。

模型实际看图并填写分析；脚本取样、校验、渲染和打开。技能本身不提供视觉模型、命令执行和文件权限，也不绑定额外视觉 API key。

最低依赖：Python 3.10+、Pillow、ffmpeg、ffprobe。先 doctor，缺项再按宿主允许方式补齐。自带常用简体中文字体；缺字报错时用 --font 指定完整中文字体。字体由 Noto Sans SC 子集化并改名 VideoNotes SC，附 SIL OFL。

macOS 用 open，Windows 用 os.startfile，Linux 仅在 DISPLAY/WAYLAND_DISPLAY 图形会话中用 xdg-open。open_result.json 的 requested 只表示系统接受请求，不保证窗口已显示或开始播放。--no-local-open 可明确禁用云端打开。

远程路径或命令被拒绝时遵守边界，不改用另一种命令绕过。云端产物通过宿主文件功能交付，不把云端打开当作用户本机打开。

原画面下方增加讲解区，输出画幅随之变化，这是学习副本。默认保留原速原声，不自动插入慢放或旁白。

探店混剪时，按实际素材标为真实视频、可保留原片、需要生成或补拍。把生成素材的起止状态与左右真实素材对照，分别写生成与剪辑要求。本技能不默认付费生成或修改原剪辑工程。
