; SealBox 封印盒 Windows 安装器（NSIS 3 + MUI2，简体中文）
; 构建：makensis /DSRCDIR=<项目根目录> packaging\installer\SealBox.nsi

Unicode true
!include "MUI2.nsh"

!ifndef SRCDIR
  !define SRCDIR "..\.."
!endif

!define APPNAME "SealBox 封印盒"
!define APPVERSION "0.1.0"
!define APPEXE "SealBox.exe"
!define PUBLISHER "SealBox"
!define APPURL "https://github.com/789564321/sealbox"

Name "${APPNAME}"
OutFile "${SRCDIR}\dist\SealBoxSetup-${APPVERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\SealBox"
InstallDirRegKey HKCU "Software\SealBox" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64

VIProductVersion "0.1.0.0"
VIAddVersionKey "ProductName" "${APPNAME}"
VIAddVersionKey "FileVersion" "${APPVERSION}"
VIAddVersionKey "ProductVersion" "${APPVERSION}"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "LegalCopyright" "MIT License"
VIAddVersionKey "FileDescription" "${APPNAME} 安装程序"

!define MUI_ABORTWARNING
!define MUI_ICON "${SRCDIR}\packaging\sealbox.ico"
!define MUI_UNICON "${SRCDIR}\packaging\sealbox.ico"
!define MUI_WELCOMEPAGE_TITLE "欢迎安装 ${APPNAME}"
!define MUI_WELCOMEPAGE_TEXT "本向导将把 ${APPNAME} 安装到你的电脑。$\r$\n$\r$\nSealBox 用一次性 UUID 密码把文件加密成 ZIP / 7z / 自解压程序，并生成密码 TXT。$\r$\n$\r$\n安装目录默认在当前用户下，不需要管理员权限。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\SealBox\SealBox.exe"
!define MUI_FINISHPAGE_RUN_TEXT "启动 ${APPNAME}"
!define MUI_FINISHPAGE_LINK "打开项目主页"
!define MUI_FINISHPAGE_LINK_LOCATION "${APPURL}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${SRCDIR}\LICENSE"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; ---------- 主程序（必装） ----------
Section "SealBox 主程序" SEC_MAIN
  SectionIn RO

  ; 如果旧版本正在运行，先结束，避免文件占用
  nsExec::Exec 'taskkill /IM ${APPEXE} /F'

  SetOutPath "$INSTDIR"
  SetOutPath "$INSTDIR\SealBox"
  File /r "${SRCDIR}\dist\SealBox\*.*"

  SetOutPath "$INSTDIR\SealBoxCLI"
  File /r "${SRCDIR}\dist\SealBoxCLI\*.*"

  SetOutPath "$INSTDIR\docs"
  File "${SRCDIR}\README.md"
  File "${SRCDIR}\LICENSE"
  File "${SRCDIR}\docs\SealBox使用说明书.pdf"

  CreateDirectory "$SMPROGRAMS\SealBox"
  CreateShortCut "$SMPROGRAMS\SealBox\SealBox.lnk" "$INSTDIR\SealBox\SealBox.exe"
  CreateShortCut "$SMPROGRAMS\SealBox\卸载 SealBox.lnk" "$INSTDIR\Uninstall.exe"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "Software\SealBox" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SealBox" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SealBox" "DisplayVersion" "${APPVERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SealBox" "Publisher" "${PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SealBox" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SealBox" "DisplayIcon" "$INSTDIR\SealBox\SealBox.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SealBox" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SealBox" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SealBox" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SealBox" "NoRepair" 1
SectionEnd

; ---------- 可选：右键菜单 ----------
Section "注册右键菜单" SEC_MENU
  nsExec::Exec '"$INSTDIR\SealBoxCLI\SealBoxCLI.exe" --install-menu'
SectionEnd

; ---------- 可选：开机自启动 ----------
Section /o "开机自启动（托盘）" SEC_AUTOSTART
  nsExec::Exec '"$INSTDIR\SealBoxCLI\SealBoxCLI.exe" --autostart enable'
SectionEnd

; ---------- 可选：桌面快捷方式 ----------
Section /o "创建桌面快捷方式" SEC_DESKTOP
  CreateShortCut "$DESKTOP\SealBox.lnk" "$INSTDIR\SealBox\SealBox.exe"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_MAIN} "窗口版、命令行版与使用说明书（约 250 MB）。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_MENU} "在文件、文件夹、文件夹空白处添加「SealBox 加密 / 解压…」。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_AUTOSTART} "登录时静默驻留系统托盘。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP} "在桌面创建 SealBox 快捷方式。"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ---------- 卸载 ----------
Section "Uninstall"
  nsExec::Exec '"$INSTDIR\SealBoxCLI\SealBoxCLI.exe" --uninstall-menu'
  nsExec::Exec '"$INSTDIR\SealBoxCLI\SealBoxCLI.exe" --autostart disable'

  Delete "$SMPROGRAMS\SealBox\SealBox.lnk"
  Delete "$SMPROGRAMS\SealBox\卸载 SealBox.lnk"
  RMDir "$SMPROGRAMS\SealBox"
  Delete "$DESKTOP\SealBox.lnk"

  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\SealBox"
  DeleteRegKey HKCU "Software\SealBox"

  RMDir /r "$INSTDIR"
SectionEnd
