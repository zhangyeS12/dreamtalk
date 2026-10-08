; Lifecycle hooks supplement Tauri's owned-file uninstall and shortcut handling.
; No app-data removal, registry scanning or arbitrary portable-directory deletion.
!macro NSIS_HOOK_PREINSTALL
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
