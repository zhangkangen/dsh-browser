; dsh-browser 安装器脚本（Inno Setup 6）
; 版本号来自 version.txt，构建时用 iscc /DMyAppVersion=x.y.z 覆盖
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

[Setup]
AppName=DeepSeek Harness 浏览器容器
AppVersion={#MyAppVersion}
AppVerName=DeepSeek Harness 浏览器容器 {#MyAppVersion}
AppPublisher=DeepSeek Harness
DefaultDirName={localappdata}\dsh-browser
DefaultGroupName=DeepSeek Harness
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=dsh-browser-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\dsh-browser\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Icons]
Name: "{autoprograms}\DeepSeek Harness"; Filename: "{app}\dsh-browser.exe"
Name: "{autodesktop}\DeepSeek Harness"; Filename: "{app}\dsh-browser.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\dsh-browser.exe"; Description: "启动 DeepSeek Harness"; Flags: nowait postinstall skipifsilent
