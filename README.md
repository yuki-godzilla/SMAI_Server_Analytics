# SMAI Server Operations

SMAI譛ｬ菴薙→縺ｯ蛻・屬縺励◆縲仝indows蟶ｸ譎る°逕ｨ逕ｨ縺ｮ逶｣隕悶・繝舌ャ繧ｯ繧｢繝・・繝ｻ髫懷ｮｳ隗｣譫舌Μ繝昴ず繝医Μ縺ｧ縺吶・
## 蠖ｹ蜑ｲ

- SMAI Streamlit縺ｮL1縲廰3繝倥Ν繧ｹ繝√ぉ繝・け
- Windows繝・せ繧ｯ繝医ャ繝嶺ｸ翫・驕狗畑逶｣隕也判髱｢
- 繝ｦ繝ｼ繧ｶ繝ｼ繝ｭ繧ｰ繧､繝ｳ縲∝ｮ溯｡御ｸｭ蜃ｦ逅・√Γ繝ｳ繝・リ繝ｳ繧ｹ迥ｶ諷九∫峩霑代Ο繧ｰ縺ｮ陦ｨ遉ｺ
- 譛ｬ菴薙・繝ｦ繝ｼ繧ｶ繝ｼ繝・・繧ｿ繝ｻ驕狗畑迥ｶ諷九・豁｣蠑上↑驫俶氛繝槭せ繧ｿ繝ｼ縺ｮ繝舌ャ繧ｯ繧｢繝・・
- 繝ｭ繧ｰ縺ｮ菫晄戟譛滄俣繝ｻ螳ｹ驥冗ｮ｡逅・
譛ｬ繝ｪ繝昴ず繝医Μ縺ｯSMAI譛ｬ菴薙ｒ螟画峩縺励∪縺帙ｓ縲ＡSMAI_PROJECT_ROOT`縺ｧ譛ｬ菴薙ヱ繧ｹ繧呈欠螳壹＠縲√Ο繧ｰ繝ｻ繝舌ャ繧ｯ繧｢繝・・縺ｯ`SMAI_RUNTIME_ROOT`縺ｸ菫晏ｭ倥＠縺ｾ縺吶・
## 襍ｷ蜍・
```powershell
$env:SMAI_PROJECT_ROOT = "C:\Users\user\workspace\SMAI_Projects\Smart_Market_AI"
$env:SMAI_RUNTIME_ROOT = "C:\Users\user\workspace\SMAI_Projects\SMAI_Server_Runtime"
python .\dashboard.py
```

螟夜Κ萓晏ｭ倥↑縺励・Tkinter逕ｻ髱｢縺ｧ縺吶４MAI譛ｬ菴薙′蛛懈ｭ｢縺励※縺・※繧ら判髱｢縺ｯ谿九ｊ縲∵怙蠕後・迥ｶ諷九→繝ｭ繧ｰ繧定｡ｨ遉ｺ縺ｧ縺阪∪縺吶・

## Backup operations

```powershell
# Create a backup
python .\backup.py create

# Verify a backup
python .\backup.py verify <backup-path>

# Restore from a backup
python .\backup.py restore <backup-path>

# Restore into an isolated directory for a smoke check
python .\backup.py restore <backup-path> --destination <restore-directory>

# Create, verify, restore to a temporary isolated directory, and hash-check it
python .\backup.py smoke
```

- `create` creates a timestamped backup under the runtime backup directory.
- `create` exits unsuccessfully if the resulting manifest cannot be verified; an incomplete backup is never reported as restorable.
- `verify` checks the manifest, file hashes, and that every manifest path remains inside the backup.
- `restore` performs the same verification before copying. If any file is missing, changed, skipped, or outside the backup, it aborts before writing a destination file.
- Use `--destination` to restore into an isolated directory before considering a production restore. Without it, files are copied back to the project data directories.
- `smoke` never writes into the SMAI project. It records the latest result in Runtime after the backup, manifest, isolated restore, and restored-file hashes all verify.
- If a source file cannot be copied because it is locked, it is recorded as skipped in the manifest and the backup still completes.
- Transient `.tmp` files and `.lock` files are excluded because they are neither durable state nor safe restore input.

## Runtime retention

```powershell
# Inspect only; no runtime files are removed.
python .\retention.py --dry-run

# Apply the local retention policy.
python .\retention.py
```

Retention removes only expired files directly under `Runtime/logs/` and complete,
tool-created backup directories named `smai_*` with a `manifest.json`.  Incomplete
or manually named backup directories are left untouched for operator review.

## Always-on dashboard

The Analytics console follows the SMAI dark navy / cyan visual language and refreshes health, sessions, operations, tasks, incidents, and recent logs every five seconds. Its Overview includes a service topology map, a 0-100 health gauge, a health timeline, and an L1/L2/L3 check matrix. These visuals describe operations only; they do not calculate or interpret investment results.

Register it to open automatically after the interactive Windows user logs on:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\register_smai_analytics_autostart_task.ps1
```

The task starts `run_dashboard.bat` after a one-minute delay. This is intentionally an interactive logon task so that the Tkinter window is visible to the operator. To remove it:

```powershell
.\scripts\unregister_smai_analytics_autostart_task.ps1
```

To restart only the local Analytics dashboard without stopping SMAI Streamlit,
run `restart_dashboard.bat`. It identifies Python processes by the absolute
`dashboard.py` path, then starts the standard dashboard launcher again.

## Critical incident operations

`incident_automation.py` converts only fail-closed `critical` health conditions
into local Codex investigation requests. It stores the request, improvement
report, and administrator-mail outbox under `SMAI_Server_Runtime` and never
changes SMAI source code automatically. See
[`Documents/08_Incident_Automation_Operations.md`](Documents/08_Incident_Automation_Operations.md)
for the 5-minute task registration, report completion, and opt-in SMTP delivery
procedure.
