// umahook.dll — DLL de captura inyectable en umamusume.exe (DMM) ya corriendo.
// No es proxy ni toca archivos del juego: se inyecta en el proceso vivo.
// Hookea curl_easy_setopt (UnityPlayer.dll RVA 0x1797fa0) y captura el API:
//   api_<seq>_url.txt / _req.bin / _resp.bin  en umma\capture\

#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <string>
#include <map>
#include "MinHook.h"

static const wchar_t* CAP_DIR=L"E:\\Documentos\\princess connect\\umma\\capture";
static volatile LONG g_seq=0;
static CRITICAL_SECTION g_cs;
static const DWORD CURL_SETOPT_RVA=0x1797fa0;
enum { OPT_WRITEDATA=10001, OPT_URL=10002, OPT_READDATA=10009, OPT_WRITEFUNCTION=20011, OPT_READFUNCTION=20012 };

static void marker(const char* m){ wchar_t fn[MAX_PATH]; swprintf(fn,MAX_PATH,L"%s\\umaproxy_loaded.txt",CAP_DIR); HANDLE f=CreateFileW(fn,GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr); if(f!=INVALID_HANDLE_VALUE){DWORD w;WriteFile(f,m,(DWORD)strlen(m),&w,nullptr);CloseHandle(f);} }
static void append(const wchar_t* name,const void* p,size_t len){ if(!p||!len||len>(64u*1024*1024))return; wchar_t fn[MAX_PATH]; swprintf(fn,MAX_PATH,L"%s\\%s",CAP_DIR,name); HANDLE f=CreateFileW(fn,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr); if(f==INVALID_HANDLE_VALUE)return; SetFilePointer(f,0,nullptr,FILE_END); DWORD w; __try{WriteFile(f,p,(DWORD)len,&w,nullptr);}__except(EXCEPTION_EXECUTE_HANDLER){} CloseHandle(f); }
static void writenew(const wchar_t* name,const void* p,size_t len){ wchar_t fn[MAX_PATH]; swprintf(fn,MAX_PATH,L"%s\\%s",CAP_DIR,name); HANDLE f=CreateFileW(fn,GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr); if(f==INVALID_HANDLE_VALUE)return; DWORD w; WriteFile(f,p,(DWORD)len,&w,nullptr); CloseHandle(f); }

typedef size_t (*iofn_t)(char*,size_t,size_t,void*);
struct Rec{ long seq=0; iofn_t readfn=nullptr; iofn_t writefn=nullptr; };
static std::map<void*,Rec>* g_byCurl=nullptr; static std::map<void*,Rec*>* g_byRead=nullptr; static std::map<void*,Rec*>* g_byWrite=nullptr;
static size_t w_read(char* buf,size_t size,size_t nitems,void* ud){ iofn_t o=nullptr; long s=0; EnterCriticalSection(&g_cs); auto it=g_byRead->find(ud); if(it!=g_byRead->end()){o=it->second->readfn;s=it->second->seq;} LeaveCriticalSection(&g_cs); size_t n=o?o(buf,size,nitems,ud):0; if(n&&s){wchar_t nm[64];swprintf(nm,64,L"api_%05ld_req.bin",s);append(nm,buf,n);} return n; }
static size_t w_write(char* ptr,size_t size,size_t nmemb,void* ud){ iofn_t o=nullptr; long s=0; EnterCriticalSection(&g_cs); auto it=g_byWrite->find(ud); if(it!=g_byWrite->end()){o=it->second->writefn;s=it->second->seq;} LeaveCriticalSection(&g_cs); size_t b=size*nmemb; if(b&&s){wchar_t nm[64];swprintf(nm,64,L"api_%05ld_resp.bin",s);append(nm,ptr,b);} return o?o(ptr,size,nmemb,ud):b; }

typedef int (*setopt_t)(void*,int,void*); static setopt_t o_setopt=nullptr;
static int h_setopt(void* curl,int option,void* param){
    EnterCriticalSection(&g_cs);
    Rec& r=(*g_byCurl)[curl];
    if(option==OPT_URL&&param){ r.seq=InterlockedIncrement(&g_seq); const char* u=(const char*)param; wchar_t nm[64];swprintf(nm,64,L"api_%05ld_url.txt",r.seq);writenew(nm,u,strlen(u)); }
    else if(option==OPT_READFUNCTION){ r.readfn=(iofn_t)param; }
    else if(option==OPT_READDATA){ (*g_byRead)[param]=&r; }
    else if(option==OPT_WRITEFUNCTION){ r.writefn=(iofn_t)param; }
    else if(option==OPT_WRITEDATA){ (*g_byWrite)[param]=&r; }
    LeaveCriticalSection(&g_cs);
    if(option==OPT_READFUNCTION&&param)  return o_setopt(curl,option,(void*)&w_read);
    if(option==OPT_WRITEFUNCTION&&param) return o_setopt(curl,option,(void*)&w_write);
    return o_setopt(curl,option,param);
}

static DWORD WINAPI init_hooks(LPVOID){
    HMODULE up=nullptr; for(int i=0;i<1200&&!up;i++){ up=GetModuleHandleW(L"UnityPlayer.dll"); if(!up)Sleep(100);}
    if(!up){ marker("umahook: UnityPlayer no encontrado"); return 0; }
    void* tgt=(void*)((uintptr_t)up+CURL_SETOPT_RVA);
    MH_STATUS mi=MH_Initialize(); MH_STATUS c=MH_CreateHook(tgt,&h_setopt,(LPVOID*)&o_setopt); MH_STATUS e=MH_EnableHook(tgt);
    char st[160]; int k=_snprintf_s(st,sizeof(st),_TRUNCATE,"umahook setopt=%p init=%d create=%d enable=%d",tgt,mi,c,e); writenew(L"_hookstatus.txt",st,k);
    return 0;
}

BOOL APIENTRY DllMain(HMODULE h,DWORD reason,LPVOID){
    if(reason==DLL_PROCESS_ATTACH){
        DisableThreadLibraryCalls(h); InitializeCriticalSection(&g_cs);
        g_byCurl=new std::map<void*,Rec>(); g_byRead=new std::map<void*,Rec*>(); g_byWrite=new std::map<void*,Rec*>();
        CreateDirectoryW(CAP_DIR,nullptr);
        marker("umahook inyectado OK");
        CreateThread(nullptr,0,init_hooks,nullptr,0,nullptr);
    }
    return TRUE;
}
