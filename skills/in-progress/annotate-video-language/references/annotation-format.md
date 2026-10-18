# 标注格式

从 prepare 输出的 analysis.template.json 填写。时间以视频首个可见画面为零，单位为秒；区间左闭右开。保留 source 的指纹和时长。

review.visual 为 pending 或 complete，渲染只接受 complete；review.audio 为 listened、unavailable 或 no-audio。

每条 shot 的字段：

```json
{"id":"S001","start":0,"end":4,"observed":"实际观察","terms":["中景","平视"],"subject_motion":"主体动作","camera_motion":"运镜；不确定则明确写无法区分","depth":"景深效果或无法判断","confidence":"high","evidence":[{"time":0.1,"file":"frames/f0001.jpg"},{"time":2,"file":"frames/f0002.jpg"}],"generation_prompt":"中文生成描述","edit_instruction":"真实素材截取与处理建议"}
```

shots 按时间顺序完整覆盖视频，无空隙重叠；相邻边界使用同一个数值，避免小数空隙。视频结束时间可容差一帧。每镜至少两个不同时刻的有效证据；运动镜头须检查前、中、后三个。极短单帧镜头可用一个证据，注明限制。

全部相邻镜头各有一条 join，一镜到底 joins 为空：

```json
{"id":"J001","from_shot":"S001","to_shot":"S002","start":3.7,"end":4.3,"cut_time":4,"type":"硬切，动作衔接","observed":"前镜结束状态；后镜开始状态","continuity":"动作、方向、位置怎样对应","confidence":"medium","evidence":[{"time":3.9,"file":"frames/f0010.jpg"},{"time":4.1,"file":"frames/f0011.jpg"}],"generation_constraints":"补生成素材的起止条件","edit_instruction":"截在哪里，怎样连接","audio_observed":"未试听，声音衔接待核对"}
```

join.start/end 是衔接检查区间，必须包含 cut_time；cut_time 与镜头表相邻边界一致。叠化等重叠区只归入一段 shot，在 join 中记录完整区间和效果。

evidence.file 是相对 analysis.json 的现有图片路径，也可引用实际绝对路径。时间需落在对应镜头/接点及全片范围内。脚本只读取图片，不执行文件内容。

以上仅为字段示例，省略了 S002，不能直接渲染。中文文案写具体观察与方法，未知项不留空。视频讲解区空间不足时明确提示续见说明文档，完整指令在报告中保留。
