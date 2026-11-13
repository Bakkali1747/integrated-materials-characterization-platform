#ifndef AppVersion
  #define AppVersion "0.14.0"
#endif

[Setup]
AppId={{B0EEE48D-E004-4D17-AF64-91E449DC3152}
AppName=综合材料表征分析平台
AppVersion={#AppVersion}
AppPublisher=Yunxuan Fang
DefaultDirName={localappdata}\Programs\IntegratedMaterialsCharacterizationPlatform
DefaultGroupName=综合材料表征分析平台
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\output\releases
OutputBaseFilename=MaterialsCharacterizationPlatform-Setup-{#AppVersion}-win64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\IntegratedMaterialsCharacterizationPlatform.exe
DisableProgramGroupPage=yes
CloseApplications=yes
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce

[Files]
Source: "..\output\dist\IntegratedMaterialsCharacterizationPlatform\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\综合材料表征分析平台"; Filename: "{app}\IntegratedMaterialsCharacterizationPlatform.exe"
Name: "{userdesktop}\综合材料表征分析平台"; Filename: "{app}\IntegratedMaterialsCharacterizationPlatform.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\IntegratedMaterialsCharacterizationPlatform.exe"; Description: "启动综合材料表征分析平台"; Flags: nowait postinstall skipifsilent

; 用户结果与日志在程序目录之外，卸载不删除科研数据。
