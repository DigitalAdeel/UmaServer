@echo off
set VS=C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "%~dp0"
set MH=..\..\tools\minhook
echo --- compilando umahook.dll ---
cl /nologo /LD /O2 /MT /EHsc /I "%MH%\include" hook.cpp "%MH%\src\hook.c" "%MH%\src\buffer.c" "%MH%\src\trampoline.c" "%MH%\src\hde\hde64.c" "%MH%\src\hde\hde32.c" /Fe:umahook.dll /link /OUT:umahook.dll
echo HOOK_EXIT=%ERRORLEVEL%
echo --- compilando umainject.exe ---
cl /nologo /O2 /MT /EHsc inject.cpp /Fe:umainject.exe
echo INJECT_EXIT=%ERRORLEVEL%
