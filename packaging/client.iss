#ifndef AppVersion
  #define AppVersion "0.11.0"
#endif

[Setup]
AppId={{0C3356A8-E268-4BFA-9F5D-F2C6B95468B0}
AppName=微波吸收材料分析软件
AppVersion={#AppVersion}
AppPublisher=Yunxuan Fang
DefaultDirName={localappdata}\Programs\MicrowaveAbsorptionAnalyzer
DefaultGroupName=微波吸收材料分析软件
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\output\releases
OutputBaseFilename=MicrowaveAbsorptionAnalyzer-Setup-{#AppVersion}-win64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\MicrowaveAbsorptionAnalyzer.exe
DisableProgramGroupPage=yes
CloseApplications=yes
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce

[Files]
Source: "..\output\dist\MicrowaveAbsorptionAnalyzer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\微波吸收材料分析软件"; Filename: "{app}\MicrowaveAbsorptionAnalyzer.exe"
Name: "{userdesktop}\微波吸收材料分析软件"; Filename: "{app}\MicrowaveAbsorptionAnalyzer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MicrowaveAbsorptionAnalyzer.exe"; Description: "启动微波吸收材料分析软件"; Flags: nowait postinstall skipifsilent

; 用户结果与日志在程序目录之外，卸载不删除科研数据。
