#ifndef MyAppName
  #define MyAppName "Branching Novel Editor"
#endif
#ifndef MyAppExe
  #define MyAppExe "BranchingNovelEditor.exe"
#endif
#ifndef ReleaseAssetPattern
  #define ReleaseAssetPattern "editor"
#endif

; ★ 여기서는 GUID만 맨몸으로
#ifndef MyAppGuid
  #define MyAppGuid "667FEBC7-64DB-446E-97B5-E6886D5E4660"
#endif

#define InstallEditor 1
#define InstallGame 0

#include "installer.iss"
