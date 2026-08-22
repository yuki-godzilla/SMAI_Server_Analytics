# SMAI Web Workspace Startup

## Canonical UI

The canonical Operations UI is the Web Analytics console on `http://localhost:8502`. The former Tkinter dashboard and visible PowerShell service prompts are not part of the supported startup path.

The local Windows workspace contains exactly two user-facing browser apps:

| Rightmost monitor left 50% | Rightmost monitor right 50% |
| --- | --- |
| Smart Market AI `http://localhost:8501` | SMAI Analytics `http://localhost:8502` |

No VS Code, CMD, PowerShell, Python, Streamlit, watcher, scheduler, or status-prompt window is arranged as part of the workspace.

## Startup responsibilities

The main Smart Market AI repository owns the hidden `SmartMarketAI-Runtime` and watcher. This repository owns:

- the hidden Analytics service startup
- readiness gating for ports 8501 and 8502
- browser app-window opening/reuse
- rightmost-monitor selection
- 50/50 WorkArea-based placement
- workspace logging

`start_smai_operations_workspace.ps1` does not start visible status prompts. It waits for services through `open_smai_service_pages.ps1` and then runs `arrange_smai_operations_workspace.ps1`.

## Browser behavior

When Google Chrome is available, each service is opened with `--app=<url>`, which removes normal browser chrome such as the address and bookmark bars. Existing matching Chrome windows are reused instead of creating duplicates.

The readiness endpoints are:

- `http://127.0.0.1:8501/_stcore/health`
- `http://127.0.0.1:8502/_stcore/health`

A page is not opened until its health endpoint responds successfully within the bounded startup window.

## Monitor placement

The workspace selects the Windows screen whose `WorkingArea.Right` is greatest. It does not rely on a fixed monitor number, fixed resolution, or the primary-display flag.

The selected `WorkingArea` is split into two rectangles using its actual X/Y/Width/Height. This keeps placement compatible with differing resolutions, taskbar sizes, display scaling, and changes to the primary monitor.

## Runtime lifecycle and health

The main runtime publishes `data/ops/server_ops/runtime_lifecycle.json` with phases:

- `STARTING`
- `READY`
- `DEGRADED`
- `CRITICAL`
- `STOPPING`

Analytics treats a fresh `STARTING` or `STOPPING` phase as an expected transition only when the failing continuity checks are limited to the main 8501 entrypoint. Persistence, disk, or other L3 failures are never hidden by the startup grace period. A stale `STARTING` state reverts to normal incident classification.

The Web console renders `starting` as `準備中` and `stopping` as `停止処理中`, rather than showing a normal boot as a critical 18/100 incident.

## Registering Analytics and Workspace

From a PowerShell session in the Analytics repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\register_smai_analytics_autostart_task.ps1
.\scripts\register_smai_operations_workspace_task.ps1 -RunImmediately
```

Both Startup launchers use hidden PowerShell. The registration removes the legacy CMD Startup launchers when present. Analytics registration also disables the legacy `SMAI-Server-Analytics` scheduled task when it still points to the old BAT launcher.

Re-running the workspace launcher is safe: healthy existing Web windows are reused and then returned to the correct rightmost-monitor layout.

## Logs

Workspace activity is written to:

```text
logs/workspace.log
```

Analytics service/runtime logs remain under the existing Runtime/log directories. Visible command windows are not used for diagnostics.

## Windows deployment validation

After pulling the merged changes on the server PC, validate after logoff/logon or reboot:

1. No visible command or PowerShell status window appears.
2. 8501 and 8502 become healthy before their Web windows open.
3. Only the two Web apps appear as the SMAI local workspace.
4. Both windows are on the rightmost monitor and split its WorkArea 50/50.
5. Re-running the workspace does not create duplicate app windows and restores the layout if moved.
6. A fresh runtime `STARTING` state displays as preparation, not a critical incident.
7. A stale startup or genuine L3 failure still becomes degraded/critical as appropriate.
8. LAN/Tailscale access to both services remains unchanged.
