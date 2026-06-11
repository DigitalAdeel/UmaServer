// umainject.exe — inyecta umahook.dll en umamusume.exe (DMM) ya corriendo.
// Espera a que el proceso exista, luego CreateRemoteThread(LoadLibraryW).
// Uso: umainject.exe [ruta_dll]   (por defecto umahook.dll junto al exe)

#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>
#include <string>

static DWORD find_pid(const wchar_t* name){
    DWORD pid=0; HANDLE snap=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    if(snap==INVALID_HANDLE_VALUE) return 0;
    PROCESSENTRY32W pe={sizeof(pe)};
    if(Process32FirstW(snap,&pe)){ do{ if(_wcsicmp(pe.szExeFile,name)==0){ pid=pe.th32ProcessID; break; } }while(Process32NextW(snap,&pe)); }
    CloseHandle(snap); return pid;
}

int wmain(int argc,wchar_t** argv){
    // ruta del DLL
    wchar_t dll[MAX_PATH];
    if(argc>1){ wcscpy_s(dll,argv[1]); }
    else { GetModuleFileNameW(nullptr,dll,MAX_PATH); wchar_t* s=wcsrchr(dll,L'\\'); if(s){ wcscpy_s(s+1,MAX_PATH-(s+1-dll),L"umahook.dll"); } }
    if(GetFileAttributesW(dll)==INVALID_FILE_ATTRIBUTES){ wprintf(L"[!] No existe el DLL: %s\n",dll); return 1; }
    wprintf(L"[*] DLL a inyectar: %s\n",dll);

    wprintf(L"[*] Esperando proceso umamusume.exe...\n");
    DWORD pid=0; for(int i=0;i<600 && !(pid=find_pid(L"umamusume.exe"));i++) Sleep(500);
    if(!pid){ wprintf(L"[!] umamusume.exe no encontrado (timeout)\n"); return 1; }
    wprintf(L"[*] PID=%lu. Inyectando...\n",pid);

    HANDLE p=OpenProcess(PROCESS_CREATE_THREAD|PROCESS_VM_OPERATION|PROCESS_VM_WRITE|PROCESS_VM_READ|PROCESS_QUERY_INFORMATION,FALSE,pid);
    if(!p){ wprintf(L"[!] OpenProcess fallo (%lu)\n",GetLastError()); return 1; }
    SIZE_T sz=(wcslen(dll)+1)*sizeof(wchar_t);
    void* rem=VirtualAllocEx(p,nullptr,sz,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if(!rem){ wprintf(L"[!] VirtualAllocEx fallo\n"); CloseHandle(p); return 1; }
    WriteProcessMemory(p,rem,dll,sz,nullptr);
    HMODULE k32=GetModuleHandleW(L"kernel32.dll");
    auto load=(LPTHREAD_START_ROUTINE)GetProcAddress(k32,"LoadLibraryW");
    HANDLE t=CreateRemoteThread(p,nullptr,0,load,rem,0,nullptr);
    if(!t){ wprintf(L"[!] CreateRemoteThread fallo (%lu)\n",GetLastError()); CloseHandle(p); return 1; }
    WaitForSingleObject(t,5000);
    DWORD ec=0; GetExitCodeThread(t,&ec);
    wprintf(L"[+] Inyectado. LoadLibraryW devolvio modulo=0x%lx\n",ec);
    VirtualFreeEx(p,rem,0,MEM_RELEASE);
    CloseHandle(t); CloseHandle(p);
    return 0;
}
