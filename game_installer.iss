#ifndef MyAppName
  #define MyAppName "Branching Novel"
#endif
#ifndef MyAppExe
  #define MyAppExe "BranchingNovel.exe"
#endif
#ifndef ReleaseAssetPattern
  #define ReleaseAssetPattern "game"
#endif

; ★ 여기서도 맨몸 GUID만
#ifndef MyAppGuid
  #define MyAppGuid "0FD4DF37-F7B3-40B1-8715-9667977A8D51"
#endif

#define InstallEditor 0
#define InstallGame 1

#include "installer.iss"
