# SMAI Server Analytics - Project Context

## Purpose

SMAI譛ｬ菴薙ｒWindows PC荳翫〒蟶ｸ譎る°逕ｨ縺吶ｋ縺溘ａ縺ｮ縲∫峡遶九＠縺溽屮隕悶・繝舌ャ繧ｯ繧｢繝・・繝ｻ髫懷ｮｳ隗｣譫舌・繝ｭ繧ｸ繧ｧ繧ｯ繝医〒縺吶・
## Current status

- `dashboard.py`: Tkinter縺ｮ繝・せ繧ｯ繝医ャ繝礼屮隕也判髱｢縲・遘帝俣髫斐〒health snapshot縲《ession縲｛peration縲∫峩霑代Ο繧ｰ繧呈峩譁ｰ
- `health.py`: L1 TCP/Streamlit health縲´2繝壹・繧ｸ蠢懃ｭ斐´3 state/data read-write縺ｮ3谿ｵ髫守｢ｺ隱・- `backup.py`: user data縲《erver ops state縲∵ｭ｣蠑上↑symbol universe繧坦untime縺ｸmanifest莉倥″繝舌ャ繧ｯ繧｢繝・・
- `retention.py`: Runtime繝ｭ繧ｰ縺ｮ菫晄戟譛滄剞蜃ｦ逅・- `retention_policy.json`: 繝ｭ繧ｰ縲√ヰ繝・け繧｢繝・・縲∫函謌舌Ξ繝昴・繝医；it霑ｽ霍｡蟇ｾ雎｡縺ｮ譁ｹ驥・- `tasks.md`: SMAI譛ｬ菴薙→驕狗畑繧ｳ繝ｳ繝昴・繝阪Φ繝医・雋ｬ蜍吩ｸ隕ｧ
- `audit.py`: secret繧帝勁螟悶＠縺滓桃菴懊う繝吶Φ繝医ｒRuntime縺ｮ`audit/events.jsonl`縺ｸ霑ｽ險・- `dashboard.py`縺ｮ`Activity History`: 繝ｦ繝ｼ繧ｶ繝ｼ縲∵桃菴懊∝ｯｾ雎｡縲∫ｵ先棡縲∫ｫｯ譛ｫ謫ｬ莨ｼID縲∵園隕∵凾髢薙ｒ陦ｨ遉ｺ

## Runtime layout

譌｢螳壼､縺ｯ谺｡縺ｮ縺ｨ縺翫ｊ縺ｧ縺吶・
```text
C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI       # SMAI譛ｬ菴・C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Analytics # 縺薙・繝ｪ繝昴ず繝医Μ
C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime   # 繝ｭ繧ｰ繝ｻ繝舌ャ繧ｯ繧｢繝・・繝ｻ螳溯｡檎憾諷・```

`SMAI_PROJECT_ROOT` 縺ｨ `SMAI_RUNTIME_ROOT` 縺ｧ螟画峩縺ｧ縺阪∪縺吶・
## Explicit boundaries

- Analytics縺ｯ譛ｬ菴薙・繝ｩ繝ｳ繧ｭ繝ｳ繧ｰ縲：orecast縲√せ繧ｳ繧｢縲√Θ繝ｼ繧ｶ繝ｼ繝・・繧ｿ繧貞､画峩縺励↑縺・- 逶｣隕也判髱｢蛛懈ｭ｢縺ｯSMAI譛ｬ菴灘●豁｢繧呈э蜻ｳ縺励↑縺・- Gateway/Ollama/騾夂衍scheduler縺ｯ莉ｻ諢丈ｾ晏ｭ倥→縺励※陦ｨ遉ｺ縺吶ｋ
- 逕滓・繝ｬ繝昴・繝医・髫懷ｮｳ隱ｿ譟ｻ逕ｨ縺ｫRuntime縺ｸ菫晏ｭ倥＠縲・壼ｸｸ縺ｯGit縺ｸ霑ｽ霍｡縺励↑縺・- 蜀咲樟諤ｧ縺ｮ縺ゅｋ驫俶氛繝槭せ繧ｿ繝ｼ縺ｨmanifest縺縺代ｒ譛ｬ菴灘・縺ｮGit縺ｧ霑ｽ霍｡縺吶ｋ

## Next priorities

1. Analytics縺ｮWindows繧ｿ繧ｹ繧ｯ逋ｻ骭ｲ繧定ｿｽ蜉
2. graceful shutdown縺ｮ譛ｬ菴馴｣謳ｺ繧貞ｮ滓ｩ溽｢ｺ隱・3. backup create/verify/restore smoke繧定ｿｽ蜉
4. 繝ｭ繧ｰ螳ｹ驥丈ｸ企剞繝ｻ蝨ｧ邵ｮ繝ｻ繧ｨ繝ｩ繝ｼ菫晄戟譛滄俣繧貞ｮ溯｣・5. symbol maintenance縺ｮ閾ｪ蜍頻ush繧壇ry-run縺ｧ遒ｺ隱榊ｾ後↓譛牙柑蛹・6. SMAI譛ｬ菴薙・繝励Ο繝輔ぅ繝ｼ繝ｫ驕ｸ謚槭√・繝ｼ繧ｸ謫堺ｽ懊∽ｸｻ隕∝・逅・∈`audit.record_event`縺ｮ騾｣謳ｺ
