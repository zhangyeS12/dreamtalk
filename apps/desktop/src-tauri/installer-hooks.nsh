; Lifecycle hooks supplement Tauri's owned-file uninstall and shortcut handling.
; No app-data removal, registry scanning or arbitrary portable-directory deletion.
Var DreamtalkBackupDone
!macro DREAMTALK_BACKUP_BEFORE_INSTALL
  ${If} $DreamtalkBackupDone != 1
    Push $R0
    Push $R1
    InitPluginsDir
    File /oname=$PLUGINSDIR\dreamtalk-save-backup.ps1 "${__FILEDIR__}\installer-save-backup.ps1"
    nsExec::ExecToStack '$\"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe$\" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $\"$PLUGINSDIR\dreamtalk-save-backup.ps1$\" -Version $\"${VERSION}$\"'
    Pop $R0
    Pop $R1
    ${If} $R0 != 0
      MessageBox MB_OK|MB_ICONSTOP "无法完成存档备份，已停止安装。请先从托盘退出 dreamtalk，并检查磁盘空间后重试。原程序和数据保持不变。"
      Abort
    ${EndIf}
    StrCpy $DreamtalkBackupDone 1
    Pop $R1
    Pop $R0
  ${EndIf}
!macroend
!macro NSIS_HOOK_PREINSTALL
  !insertmacro DREAMTALK_BACKUP_BEFORE_INSTALL
  IfFileExists "$INSTDIR\.git\HEAD" 0 +3
    MessageBox MB_OK|MB_ICONSTOP "不能安装到源码仓库，请选择应用安装目录。"
    Abort
  IfFileExists "$INSTDIR\data\runtime.sqlite3" 0 +3
    MessageBox MB_OK|MB_ICONSTOP "不能安装到存档目录，请选择应用安装目录。"
    Abort
!macroend
!macro NSIS_HOOK_POSTINSTALL
  Push $R8
  Push $R9
  ; Ensure the desktop entry points at the single fixed installation. Tauri's
  ; update mode normally preserves the existing shortcut; also repair it here.
  CreateShortcut "$DESKTOP\dreamtalk.lnk" "$INSTDIR\dreamtalk-desktop.exe" "" "$INSTDIR\dreamtalk-desktop.exe"
  ; Preserve enabled state of the one official autostart entry. Do not enable
  ; a disabled entry, and do not touch another application or startup parameter.
  ReadRegStr $R8 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "dreamtalk"
  ${If} $R8 != ""
    ${StrLoc} $R9 $R8 "dreamtalk-desktop.exe" ">"
    ${If} $R9 != ""
      WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "dreamtalk" '$\"$INSTDIR\dreamtalk-desktop.exe$\" --background'
    ${EndIf}
  ${EndIf}
  ; Foreground restart even when the previous process began with --background.
  ${If} $UpdateMode = 1
    Exec '$\"$INSTDIR\dreamtalk-desktop.exe$\"'
  ${EndIf}
  Pop $R9
  Pop $R8
!macroend
