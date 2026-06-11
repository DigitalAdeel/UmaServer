@echo off
REM Compila el proxy libnative.dll (con MinHook) usando MSVC.
set VS=C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "%~dp0"
set MH=..\..\tools\minhook
cl /nologo /LD /O2 /MT /EHsc /I "%MH%\include" ^
   dllmain.cpp ^
   "%MH%\src\hook.c" "%MH%\src\buffer.c" "%MH%\src\trampoline.c" ^
   "%MH%\src\hde\hde64.c" "%MH%\src\hde\hde32.c" ^
   /Fe:libnative.dll ^
   /link /OUT:libnative.dll
echo EXITCODE=%ERRORLEVEL%
