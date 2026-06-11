// UmaProxy — proxy de libnative.dll (Umamusume Steam Global).
// CAPTURA COMPLETA del protocolo en claro:
//  - hook curl_easy_setopt (UnityPlayer RVA 0x1797fa0): api_<seq>_url/req/resp (base64 coneshell)
//  - auto-hook (temprano) Gallop.HttpHelper.CompressRequest (req plaintext) y
//    DecompressResponse (resp plaintext): compreq_in/out, decresp_in/out (MessagePack en claro)
// Correlacion url<->plaintext: comparar el base64 (api_req == compreq_out, api_resp == decresp_in).

#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <string>
#include <map>
#include "MinHook.h"
#include "exports.h"

static HMODULE g_orig=nullptr;
static const wchar_t* CAP_DIR=L"E:\\Documentos\\princess connect\\umma\\capture";
static const wchar_t* REDIRECT_FLAG=L"E:\\Documentos\\princess connect\\umma\\REDIRECT";
static bool g_redirect=false;   // si existe el flag: bypass coneshell + redirect a 127.0.0.1:5090
static volatile LONG g_seq=0, g_cseq=0;
static CRITICAL_SECTION g_cs;
static const DWORD CURL_SETOPT_RVA=0x1797fa0;
enum { OPT_WRITEDATA=10001, OPT_URL=10002, OPT_READDATA=10009, OPT_WRITEFUNCTION=20011, OPT_READFUNCTION=20012 };

static std::wstring module_dir(HMODULE h){ wchar_t p[MAX_PATH]; GetModuleFileNameW(h,p,MAX_PATH); std::wstring s(p); size_t q=s.find_last_of(L"\\/"); return q==std::wstring::npos?L"":s.substr(0,q+1); }
static void marker(const std::wstring& d,const char* m){ HANDLE f=CreateFileW((d+L"umaproxy_loaded.txt").c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr); if(f!=INVALID_HANDLE_VALUE){DWORD w;WriteFile(f,m,(DWORD)strlen(m),&w,nullptr);CloseHandle(f);} }
static void append(const wchar_t* name,const void* p,size_t len){ if(!p||!len||len>(64u*1024*1024))return; wchar_t fn[MAX_PATH]; swprintf(fn,MAX_PATH,L"%s\\%s",CAP_DIR,name); HANDLE f=CreateFileW(fn,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr); if(f==INVALID_HANDLE_VALUE)return; SetFilePointer(f,0,nullptr,FILE_END); DWORD w; __try{WriteFile(f,p,(DWORD)len,&w,nullptr);}__except(EXCEPTION_EXECUTE_HANDLER){} CloseHandle(f); }
static void writenew(const wchar_t* name,const void* p,size_t len){ wchar_t fn[MAX_PATH]; swprintf(fn,MAX_PATH,L"%s\\%s",CAP_DIR,name); HANDLE f=CreateFileW(fn,GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr); if(f==INVALID_HANDLE_VALUE)return; DWORD w; WriteFile(f,p,(DWORD)len,&w,nullptr); CloseHandle(f); }

// forward asset downloader
typedef int (*reg_req_t)(void*,void*,const uint8_t*,uint16_t,const uint8_t*,uint16_t,uint64_t,uint64_t,uint32_t);
static reg_req_t g_reg_req=nullptr;
extern "C" __declspec(dllexport)
int tempest_register_request_raw(void* h,void* a2,const uint8_t* p1,uint16_t l1,const uint8_t* p2,uint16_t l2,uint64_t a7,uint64_t a8,uint32_t a9){ return g_reg_req?g_reg_req(h,a2,p1,l1,p2,l2,a7,a8,a9):0; }

// ---- captura API por curl ----
typedef size_t (*iofn_t)(char*,size_t,size_t,void*);
struct Rec{ long seq=0; iofn_t readfn=nullptr; iofn_t writefn=nullptr; };
static std::map<void*,Rec>* g_byCurl=nullptr; static std::map<void*,Rec*>* g_byRead=nullptr; static std::map<void*,Rec*>* g_byWrite=nullptr;
static size_t w_read(char* buf,size_t size,size_t nitems,void* ud){ iofn_t o=nullptr; long s=0; EnterCriticalSection(&g_cs); auto it=g_byRead->find(ud); if(it!=g_byRead->end()){o=it->second->readfn;s=it->second->seq;} LeaveCriticalSection(&g_cs); size_t n=o?o(buf,size,nitems,ud):0; if(n&&s){wchar_t nm[64];swprintf(nm,64,L"api_%05ld_req.bin",s);append(nm,buf,n);} return n; }
static size_t w_write(char* ptr,size_t size,size_t nmemb,void* ud){ iofn_t o=nullptr; long s=0; EnterCriticalSection(&g_cs); auto it=g_byWrite->find(ud); if(it!=g_byWrite->end()){o=it->second->writefn;s=it->second->seq;} LeaveCriticalSection(&g_cs); size_t b=size*nmemb; if(b&&s){wchar_t nm[64];swprintf(nm,64,L"api_%05ld_resp.bin",s);append(nm,ptr,b);} return o?o(ptr,size,nmemb,ud):b; }
typedef int (*setopt_t)(void*,int,void*); static setopt_t o_setopt=nullptr;
static int h_setopt(void* curl,int option,void* param){
    EnterCriticalSection(&g_cs);
    Rec& r=(*g_byCurl)[curl];
    if(option==OPT_URL&&param){ r.seq=InterlockedIncrement(&g_seq); const char* u=(const char*)param; wchar_t nm[64];swprintf(nm,64,L"api_%05ld_url.txt",r.seq);writenew(nm,u,strlen(u));
        if(g_redirect && strstr(u,"api.games.umamusume.com")){
            static __declspec(thread) char rb[1024]; const char* p=strstr(u,"/umamusume/");
            _snprintf_s(rb,sizeof(rb),_TRUNCATE,"http://127.0.0.1:5090%s", p?p:"/");
            LeaveCriticalSection(&g_cs); return o_setopt(curl,option,(void*)rb);
        }
    }
    else if(option==OPT_READFUNCTION){ r.readfn=(iofn_t)param; }
    else if(option==OPT_READDATA){ (*g_byRead)[param]=&r; }
    else if(option==OPT_WRITEFUNCTION){ r.writefn=(iofn_t)param; }
    else if(option==OPT_WRITEDATA){ (*g_byWrite)[param]=&r; }
    LeaveCriticalSection(&g_cs);
    if(option==OPT_READFUNCTION&&param)  return o_setopt(curl,option,(void*)&w_read);
    if(option==OPT_WRITEFUNCTION&&param) return o_setopt(curl,option,(void*)&w_write);
    return o_setopt(curl,option,param);
}

// ---- hooks HttpHelper.CompressRequest / DecompressResponse (plaintext) ----
static void dumpArr(const wchar_t* pfx,long n,void* arr){ if(!arr)return; size_t len=*(size_t*)((char*)arr+0x18); if(len==0||len>(64u*1024*1024))return; void* data=(char*)arr+0x20; wchar_t nm[80]; swprintf(nm,80,L"%s_%05ld.bin",pfx,n); append(nm,data,len); }
typedef void* (*m1_t)(void*,void*,void*);
static m1_t o_Compress=nullptr,o_Decompress=nullptr;
// metodos estaticos: el dato va en el 1er arg (t). dump t=in, r=out.
static void* h_Compress(void* t,void* a,void* mi){ long n=InterlockedIncrement(&g_cseq); dumpArr(L"compreq_in",n,t); if(g_redirect) return t; /*bypass: enviar plaintext*/ void* r=o_Compress(t,a,mi); dumpArr(L"compreq_out",n,r); return r; }
static void* h_Decompress(void* t,void* a,void* mi){ long n=InterlockedIncrement(&g_cseq); if(g_redirect) return t; /*bypass: la respuesta del server ya es plaintext*/ dumpArr(L"decresp_in",n,t); void* r=o_Decompress(t,a,mi); dumpArr(L"decresp_out",n,r); return r; }

typedef void* (*pp0)(); typedef void* (*pp1)(void*); typedef void* (*ppda)(void*,size_t*); typedef const char* (*pps)(void*);
typedef void* (*pfromname)(void*,const char*,const char*); typedef void* (*pmfn)(void*,const char*,int);
static bool hook_httphelper(){
    HMODULE ga=GetModuleHandleW(L"GameAssembly.dll"); if(!ga)return false;
    pp0 dom_get=(pp0)GetProcAddress(ga,"il2cpp_domain_get"); if(!dom_get)return false;
    void* dom=dom_get(); if(!dom)return false;
    ((pp1)GetProcAddress(ga,"il2cpp_thread_attach"))(dom);
    ppda dom_asm=(ppda)GetProcAddress(ga,"il2cpp_domain_get_assemblies"); pp1 asm_img=(pp1)GetProcAddress(ga,"il2cpp_assembly_get_image"); pps img_name=(pps)GetProcAddress(ga,"il2cpp_image_get_name");
    pfromname from=(pfromname)GetProcAddress(ga,"il2cpp_class_from_name"); pmfn gm=(pmfn)GetProcAddress(ga,"il2cpp_class_get_method_from_name");
    size_t na=0; void** asms=(void**)dom_asm(dom,&na); void* img=nullptr;
    for(size_t i=0;i<na;i++){ void* im=asm_img(asms[i]); const char* nm=img_name?img_name(im):""; if(nm&&strcmp(nm,"umamusume.dll")==0){img=im;break;} }
    if(!img)return false;
    void* hh=from(img,"Gallop","HttpHelper"); if(!hh)return false;
    void* mc=gm(hh,"CompressRequest",1); void* md=gm(hh,"DecompressResponse",1);
    if(!mc||!md)return false;
    void* aC=*(void**)mc; void* aD=*(void**)md;
    MH_CreateHook(aC,&h_Compress,(LPVOID*)&o_Compress); MH_EnableHook(aC);
    MH_CreateHook(aD,&h_Decompress,(LPVOID*)&o_Decompress); MH_EnableHook(aD);
    char st[128]; int k=_snprintf_s(st,sizeof(st),_TRUNCATE,"HttpHelper hooks: Compress=%p Decompress=%p",aC,aD); writenew(L"_cryptohook.txt",st,k);
    return true;
}

// ---- dump de metodos de clases del modo carrera (para RE del filtro de personajes) ----
typedef void* (*pmeth)(void*,void**); typedef const char* (*pmn)(void*); typedef uint32_t (*ppc)(void*);
static void dump_addr(const wchar_t* name, void* addr, size_t len){
    if(!addr)return; wchar_t fn[MAX_PATH]; swprintf(fn,MAX_PATH,L"%s\\%s",CAP_DIR,name);
    HANDLE f=CreateFileW(fn,GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr); if(f==INVALID_HANDLE_VALUE)return;
    __try{ DWORD w; WriteFile(f,addr,(DWORD)len,&w,nullptr); }__except(EXCEPTION_EXECUTE_HANDLER){}
    CloseHandle(f);
}
static void dump_sm_methods(){
    HMODULE ga=GetModuleHandleW(L"GameAssembly.dll"); if(!ga)return;
    pp0 dom_get=(pp0)GetProcAddress(ga,"il2cpp_domain_get"); if(!dom_get)return; void* dom=dom_get(); if(!dom)return;
    ((pp1)GetProcAddress(ga,"il2cpp_thread_attach"))(dom);
    ppda dom_asm=(ppda)GetProcAddress(ga,"il2cpp_domain_get_assemblies"); pp1 asm_img=(pp1)GetProcAddress(ga,"il2cpp_assembly_get_image"); pps img_name=(pps)GetProcAddress(ga,"il2cpp_image_get_name");
    pfromname from=(pfromname)GetProcAddress(ga,"il2cpp_class_from_name");
    pmeth getm=(pmeth)GetProcAddress(ga,"il2cpp_class_get_methods"); pmn mname=(pmn)GetProcAddress(ga,"il2cpp_method_get_name"); ppc mpc=(ppc)GetProcAddress(ga,"il2cpp_method_get_param_count");
    size_t na=0; void** asms=(void**)dom_asm(dom,&na); void* img=nullptr;
    for(size_t i=0;i<na;i++){ void* im=asm_img(asms[i]); const char* nm=img_name?img_name(im):""; if(nm&&strcmp(nm,"umamusume.dll")==0){img=im;break;} }
    if(!img)return;
    const char* classes[]={"SingleModeStartStepCardSelect","PartsCharacterCardSelect","SingleModeCardSelect","SingleModeStartViewController"};
    char* out=(char*)malloc(256*1024); size_t used=0; char line[512];
    for(auto cn:classes){
        void* k=from(img,"Gallop",cn);
        int n=_snprintf_s(line,sizeof(line),_TRUNCATE,"\n===== Gallop.%s (klass=%p) =====\n",cn,k); memcpy(out+used,line,n);used+=n;
        if(!k)continue;
        __try{
            void* it=nullptr; void* m;
            while((m=getm(k,&it))){ const char* mn=mname(m); uint32_t pc=mpc(m); void* addr=*(void**)m;
                n=_snprintf_s(line,sizeof(line),_TRUNCATE,"  %s/%u  @%p\n",mn?mn:"?",pc,addr); if(n>0&&used+n<256*1024){memcpy(out+used,line,n);used+=n;}
                // volcar bytes del codigo (descifrado en memoria) de los metodos clave del filtro
                if(addr && mn && (strcmp(mn,"CreateCharaList")==0 || strcmp(mn,"FindAvailableMemberCardId")==0 || strcmp(mn,"GetCardListIndex")==0)){
                    wchar_t bf[96]; swprintf(bf,96,L"smcode_%S.bin",mn); dump_addr(bf,addr,0x600);
                }
            }
        }__except(EXCEPTION_EXECUTE_HANDLER){}
    }
    writenew(L"_sm_methods.txt",out,used); free(out);
}
static DWORD WINAPI sm_watcher(LPVOID){
    wchar_t trg[MAX_PATH]; swprintf(trg,MAX_PATH,L"%s\\SMDUMP_NOW.txt",CAP_DIR);
    for(;;){ Sleep(1000); if(GetFileAttributesW(trg)!=INVALID_FILE_ATTRIBUTES){ DeleteFileW(trg); __try{dump_sm_methods();}__except(EXCEPTION_EXECUTE_HANDLER){} } }
    return 0;
}
static DWORD WINAPI init_hooks(LPVOID){
    HMODULE up=nullptr; for(int i=0;i<600&&!up;i++){ up=GetModuleHandleW(L"UnityPlayer.dll"); if(!up)Sleep(100);}
    if(!up){ const char* e="UnityPlayer no encontrado"; writenew(L"_hookstatus.txt",e,strlen(e)); return 0; }
    void* tgt=(void*)((uintptr_t)up+CURL_SETOPT_RVA);
    MH_STATUS mi=MH_Initialize(); MH_CreateHook(tgt,&h_setopt,(LPVOID*)&o_setopt); MH_STATUS e=MH_EnableHook(tgt);
    char st[160]; int k=_snprintf_s(st,sizeof(st),_TRUNCATE,"setopt=%p init=%d enable=%d",tgt,mi,e); writenew(L"_hookstatus.txt",st,k);
    // auto-hook HttpHelper en cuanto el runtime/clase esten listos (temprano, antes de start_session)
    for(int i=0;i<1200;i++){ __try{ if(hook_httphelper()) break; }__except(EXCEPTION_EXECUTE_HANDLER){} Sleep(200); }
    CreateThread(nullptr,0,sm_watcher,nullptr,0,nullptr);
    return 0;
}

BOOL APIENTRY DllMain(HMODULE h,DWORD reason,LPVOID){
    if(reason==DLL_PROCESS_ATTACH){
        DisableThreadLibraryCalls(h); InitializeCriticalSection(&g_cs);
        g_byCurl=new std::map<void*,Rec>(); g_byRead=new std::map<void*,Rec*>(); g_byWrite=new std::map<void*,Rec*>();
        std::wstring dir=module_dir(h);
        g_orig=LoadLibraryW((dir+L"libnative_orig.dll").c_str());
        if(g_orig) g_reg_req=(reg_req_t)GetProcAddress(g_orig,"tempest_register_request_raw");
        CreateDirectoryW(CAP_DIR,nullptr);
        g_redirect = GetFileAttributesW(REDIRECT_FLAG)!=INVALID_FILE_ATTRIBUTES;
        marker(dir, g_redirect ? "UmaProxy: MODO LIVE (bypass coneshell + redirect 5090)" : "UmaProxy: MODO captura");
        CreateThread(nullptr,0,init_hooks,nullptr,0,nullptr);
    }
    return TRUE;
}
