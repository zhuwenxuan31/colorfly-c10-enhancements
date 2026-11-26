#include "eq_model.h"
#include "c10_io_flags.h"

/* Fixed-address state reserved by the reviewed ELF builder, outside all stock
 * globals and v60 timer state. No change to the original configuration struct.
 */
typedef struct {
    unsigned initialized, lock, active_slot;
    eq_config active[2];
    eq_config pending;
    int open, selected, top, status;
    unsigned diag_enabled, diag_lock, diag_bytes, diag_stream, diag_error;
} eq_state;
#define STATE ((volatile eq_state *)0x446d00u)
#define MAGIC 0x45513031u
#define WORD(a) (*(volatile unsigned *)(a))
#define CONFIG "/mnt/memory/.c10-eq.cfg"
#define TEMP "/mnt/memory/.c10-eq.tmp"
#define DIAG_MARKER "/mnt/memory/.c10-eq-diag"
#define DIAG_LOG "/mnt/memory/.c10-eq-runtime.log"
#define DIAG_LIMIT 65536u
_Static_assert(sizeof(eq_state)<=256,"EQ state must remain in its reserved BSS");

extern int orig_open(const char *, int, int);
extern int orig_read(int, void *, unsigned);
extern int orig_write(int, const void *, unsigned);
extern int orig_close(int);
extern int orig_fsync(int);
extern int orig_unlink(const char *);
extern int orig_rename(const char *, const char *);
extern void *orig_popen(const char *, const char *);
extern char *orig_fgets(char *, int, void *);
extern void orig_blit(void *, void *, void *, void *);
extern void orig_pic(int, int, void *, void *);
extern void orig_label(int, int, const char *, void *);
extern void orig_text(int, int, void *, unsigned, const char *, void *);
extern void orig_battery(void *);
extern void orig_flip(void *);

static void lock_state(void) { while(__sync_lock_test_and_set(&STATE->lock,1u)){} }
static void unlock_state(void) { __sync_lock_release(&STATE->lock); }
static void snapshot(eq_config *c) {
    if(STATE->initialized!=MAGIC){eq_default(c);return;}
    lock_state();
    *c=STATE->active[STATE->active_slot&1u];
    unlock_state();
    if(!eq_valid(c))eq_default(c);
}
static void publish(const eq_config *c) {
    lock_state();
    unsigned next=(STATE->active_slot^1u)&1u;
    STATE->active[next]=*c;
    __sync_synchronize();
    STATE->active_slot=next;
    STATE->initialized=MAGIC;
    unlock_state();
}

/* Diagnostic IO never holds the configuration lock. A busy log is skipped
 * rather than making the playback thread wait for another logging caller.
 * No syscall/IO result can change the playback command or returned stdout.
 */
static void diag_write(const char *text,unsigned size) {
    if(!STATE->diag_enabled || !size)return;
    if(__sync_lock_test_and_set(&STATE->diag_lock,1u))return;
    unsigned used=STATE->diag_bytes;
    if(used>=DIAG_LIMIT){__sync_lock_release(&STATE->diag_lock);return;}
    if(size>DIAG_LIMIT-used)size=DIAG_LIMIT-used;
    int fd=orig_open(DIAG_LOG,O_WRONLY|O_CREAT|O_APPEND|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd>=0){
        unsigned sent=0;
        while(sent<size){
            int n=orig_write(fd,text+sent,size-sent);
            if(n<=0){STATE->diag_error=1;break;}
            sent+=(unsigned)n;
        }
        STATE->diag_bytes=used+sent;
        if(orig_close(fd)<0)STATE->diag_error=1;
    }else STATE->diag_error=1;
    __sync_lock_release(&STATE->diag_lock);
}

static void diag_init(void) {
    STATE->diag_enabled=STATE->diag_lock=STATE->diag_bytes=0;
    STATE->diag_stream=STATE->diag_error=0;
    int fd=orig_open(DIAG_MARKER,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC,0);
    if(fd<0)return;
    char marker[3];
    int n=orig_read(fd,marker,sizeof(marker));
    orig_close(fd);
    if(!((n==1 && marker[0]=='1') || (n==2 && marker[0]=='1' && marker[1]=='\n')))return;
    STATE->diag_enabled=1;
    fd=orig_open(DIAG_LOG,O_WRONLY|O_CREAT|O_TRUNC|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd>=0)orig_close(fd);else STATE->diag_error=1;
    static const char boot[]="C10_EQ_TRACE_v68 boot\n";
    diag_write(boot,sizeof(boot)-1);
}

static void *launch_logged(const eq_config *c,const char *command,const char *mode,unsigned size) {
    if(STATE->diag_enabled){
        STATE->diag_stream=0;
        char flags[]="enabled=0 preset=0\n";
        flags[8]=(char)('0'+c->enabled);flags[17]=(char)('0'+c->preset);
        diag_write(flags,sizeof(flags)-1);
        unsigned char raw[EQ_RECORD_SIZE];char hex[129];
        static const char digits[]="0123456789abcdef";
        eq_encode(c,raw);
        for(unsigned i=0;i<EQ_RECORD_SIZE;i++){
            hex[i*2]=digits[raw[i]>>4];hex[i*2+1]=digits[raw[i]&15];
        }
        hex[128]='\n';
        diag_write("config=",7);diag_write(hex,sizeof(hex));
        diag_write("command=",8);diag_write(command,size);diag_write("\n",1);
    }
    void *result=orig_popen(command,mode);
    if(STATE->diag_enabled){
        STATE->diag_stream=(unsigned)(uintptr_t)result;
        if(result)diag_write("popen=ok\n",9);else diag_write("popen=failed\n",13);
    }
    return result;
}

void eq_init(void) {
    eq_config c;
    unsigned char data[EQ_RECORD_SIZE+1];
    eq_default(&c);
    int fd=orig_open(CONFIG,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC,0);
    if(fd>=0){
        int used=0,got=0;
        while(used<(int)sizeof(data)){
            got=orig_read(fd,data+used,(unsigned)sizeof(data)-(unsigned)used);
            if(got<=0)break;
            used+=got;
        }
        orig_close(fd);
        if(got<0 || eq_decode(&c,data,(size_t)used)<0)STATE->status=2;
    }
    STATE->lock=0;
    STATE->active_slot=0;
    STATE->active[0]=c;
    STATE->active[1]=c;
    STATE->pending=c;
    STATE->open=0;
    STATE->selected=STATE->top=0;
    STATE->initialized=MAGIC;
    diag_init();
}

static int store(const eq_config *c) {
    unsigned char data[EQ_RECORD_SIZE];
    eq_encode(c,data);
    int fd=orig_open(TEMP,O_WRONLY|O_CREAT|O_TRUNC|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0)return -1;
    unsigned sent=0;
    while(sent<sizeof(data)){
        int n=orig_write(fd,data+sent,(unsigned)sizeof(data)-sent);
        if(n<=0){orig_close(fd);orig_unlink(TEMP);return -1;}
        sent+=(unsigned)n;
    }
    int flushed=orig_fsync(fd);
    int closed=orig_close(fd);
    if(flushed<0 || closed<0 || orig_rename(TEMP,CONFIG)<0){orig_unlink(TEMP);return -1;}
    return 0;
}

static int save_and_return(const eq_config *c) {
    if(store(c)<0){STATE->status=1;return 1;}
    publish(c);
    STATE->status=0;
    STATE->open=0;
    return 1;
}

/* Must remain exactly 0x450000: the app callsite can load this address in one
 * instruction while preserving the original a0=command, s4 and mode argument.
 */
__attribute__((section(".eq_entry"),used,noinline))
void *eq_popen(const char *command,const char *mode) {
    eq_config c;
    snapshot(&c);
    if(!c.enabled && !STATE->diag_enabled)return orig_popen(command,mode);
    char options[192], expanded[1024];
    int extra=eq_options(&c,options,sizeof(options));
    static const char verbose[]=" -v 2>&1";
    unsigned trace=STATE->diag_enabled?(unsigned)sizeof(verbose)-1:0;
    unsigned n=0;
    while(n<sizeof(expanded) && command[n])n++;
    if(extra<0 || (c.enabled && extra==0) || n+((unsigned)extra)+trace+1>sizeof(expanded)){
        STATE->status=3;
        return launch_logged(&c,command,mode,n);
    }
    for(unsigned i=0;i<n;i++)expanded[i]=command[i];
    for(int i=0;i<extra;i++)expanded[n+(unsigned)i]=options[i];
    for(unsigned i=0;i<trace;i++)expanded[n+(unsigned)extra+i]=verbose[i];
    unsigned size=n+(unsigned)extra+trace;
    expanded[size]=0;
    return launch_logged(&c,expanded,mode,size);
}

char *eq_fgets(char *buffer,int size,void *stream) {
    char *result=orig_fgets(buffer,size,stream);
    if(result && size>1 && STATE->diag_enabled &&
       (unsigned)(uintptr_t)stream==STATE->diag_stream){
        unsigned n=0,limit=(unsigned)size-1;
        while(n<limit && buffer[n])n++;
        diag_write(buffer,n);
    }
    return result;
}

static int language(void) {
    unsigned n=WORD(0x4463b8u);
    return n<2u?(int)n:2;
}
static const char *translated(const char *zh,const char *tw,const char *en) {
    int n=language();return n==0?zh:n==1?tw:en;
}
static const char *preset_name(int n) {
    static const char *const zh[EQ_PRESETS]={"平直","低音","人声","明亮","柔和","自定义"};
    static const char *const tw[EQ_PRESETS]={"平直","低音","人聲","明亮","柔和","自訂"};
    static const char *const en[EQ_PRESETS]={"Flat","Bass","Vocal","Bright","Soft","Custom"};
    if(n<0 || n>=EQ_PRESETS)n=0;
    return language()==0?zh[n]:language()==1?tw[n]:en[n];
}
static unsigned black(void) { return WORD(WORD(0x44475cu)); }
static void *font12(void) { return (void *)(uintptr_t)WORD(0x444b1cu); }
static void *font18(void) { return (void *)(uintptr_t)WORD(0x444b04u); }
static void value_at(int row,const char *text,void *screen) {
    orig_text(312,row*40+53,font12(),black(),text,screen);
}
static void number(char *out,int value,int suffix) {
    char reversed[12];int used=0,pos=0;
    if(value<0){out[pos++]='-';value=-value;}
    else if(suffix)out[pos++]='+';
    do{reversed[used++]=(char)('0'+value%10);value/=10;}while(value);
    while(used)out[pos++]=reversed[--used];
    if(suffix){out[pos++]='d';out[pos++]='B';}
    out[pos]=0;
}

void eq_main_draw(int row,int selected,void *screen) {
    eq_config c;snapshot(&c);
    orig_label(row,selected,translated("均衡器 EQ","均衡器 EQ","Equalizer EQ"),screen);
    void **table=(void **)(uintptr_t)WORD(0x444adcu);
    void *icon=table[selected?8:9];
    /* Same original row icon placement as the other settings. */
    int width=((int *)icon)[2],height=((int *)icon)[3];
    orig_pic(36-width/2,(row+1)*40+(40-height)/2,icon,screen);
    value_at(row,c.enabled?preset_name(c.preset):"OFF",screen);
}

int eq_open_item(int item,int key) {
    if(item!=11 || key!=106)return 0;
    eq_config c;snapshot(&c);
    STATE->pending=c;
    STATE->selected=STATE->top=0;
    STATE->open=1;
    STATE->status=0;
    return 1;
}

static const char *row_title(int row) {
    static const char *const band[EQ_BANDS]={"31 Hz","63 Hz","125 Hz","250 Hz","500 Hz","1 kHz","2 kHz","4 kHz","8 kHz","16 kHz"};
    if(row>=2 && row<12)return band[row-2];
    switch(row){
    case 0:return translated("EQ开关","EQ開關","EQ switch");
    case 1:return translated("预设","預設","Preset");
    case 12:return translated("自动预衰减","自動預衰減","Headroom");
    case 13:return translated("保存并返回","儲存並返回","Save and return");
    case 14:return translated("恢复默认","恢復預設","Reset defaults");
    default:return translated("返回不保存","返回不儲存","Cancel");
    }
}

int eq_try_draw(void *screen) {
    if(!STATE->open)return 0;
    if(WORD(0x444b34u)!=3u || WORD(0x444b5cu)!=11u){STATE->open=0;return 0;}
    int selected=STATE->selected;
    if(selected<0 || selected>15)selected=STATE->selected=0;
    int top=STATE->top;
    if(selected<top)top=selected;
    if(selected>top+6)top=selected-6;
    if(top<0)top=0;
    if(top>9)top=9;
    STATE->top=top;
    eq_config c=STATE->pending;
    if(!eq_valid(&c))eq_default(&c);
    void **list=(void **)(uintptr_t)WORD(0x444ad4u);
    orig_blit(list[2],0,screen,0);
    orig_text(120,9,font18(),black(),translated("均衡器 EQ","均衡器 EQ","Equalizer EQ"),screen);
    for(int i=0;i<7;i++){
        int row=top+i;
        if(row>15)break;
        if(row==selected)orig_pic(0,(i+1)*40-1,list[17],screen);
        orig_label(i,row==selected,row_title(row),screen);
        char value[32];value[0]=0;
        if(row==0)value_at(i,c.enabled?"ON":"OFF",screen);
        else if(row==1)value_at(i,preset_name(c.preset),screen);
        else if(row>=2 && row<12){number(value,c.gain[row-2],1);value_at(i,value,screen);}
        else if(row==12){number(value,-eq_headroom(&c),1);value_at(i,value,screen);}
        else value_at(i,">",screen);
    }
    const char *footer=translated("返回键保存，切歌生效","返回鍵儲存，切歌生效","Back saves; next track applies.");
    if(STATE->status==1)footer=translated("保存失败，设置未更改","儲存失敗，設定未變更","Save failed; unchanged");
    else if(STATE->status==2)footer=translated("配置无效，已关闭EQ","設定無效，已關閉EQ","Invalid config; EQ is off");
    else if(STATE->status==3)footer=translated("播放参数过长，保留原声","播放參數過長，保留原聲","Long command; original sound");
    orig_text(18,338,font12(),black(),footer,screen);
    orig_battery(screen);orig_flip(screen);
    return 1;
}

/* Stock key_down_proc also handles held UP/DOWN. Consume that path while
 * editing EQ so it cannot navigate the underlying factory menu. Adjust only
 * navigation on repeat; edits and save remain one action on key release.
 */
int eq_handle_down(int key,int repeated) {
    if(!STATE->open)return 0;
    if(WORD(0x444b34u)!=3u || WORD(0x444b5cu)!=11u){STATE->open=0;return 0;}
    if(key!=1 && key!=28 && key!=103 && key!=108 && key!=105 && key!=106)return 0;
    if(repeated && (key==103 || key==108)){
        int row=STATE->selected;
        if(row<0 || row>15)row=0;
        STATE->selected=(row+(key==108?1:15))%16;
    }
    return 1;
}

int eq_handle_key(int key,int repeated) {
    if(!STATE->open)return 0;
    if(WORD(0x444b34u)!=3u || WORD(0x444b5cu)!=11u){STATE->open=0;return 0;}
    if(key==28){STATE->open=0;return 1;}
    /* Match the factory settings workflow: BACK commits the edited value.
     * Explicit Cancel (row15) and the play key retain discard semantics.
     */
    if(key==1){
        eq_config c=STATE->pending;
        if(!eq_valid(&c))eq_default(&c);
        return save_and_return(&c);
    }
    int row=STATE->selected;
    if(row<0 || row>15)row=STATE->selected=0;
    if(key==103 || key==108){
        if(!repeated)STATE->selected=(row+(key==108?1:15))%16;
        return 1;
    }
    if(key!=105 && key!=106)return 0;
    eq_config c=STATE->pending;
    if(!eq_valid(&c))eq_default(&c);
    int direction=key==106?1:-1;
    if(row==0)c.enabled^=1;
    else if(row==1)eq_set_preset(&c,(c.preset+(direction>0?1:EQ_PRESETS-1))%EQ_PRESETS);
    else if(row>=2 && row<12)eq_adjust(&c,row-2,direction);
    else if(row==13 && key==106){
        return save_and_return(&c);
    }else if(row==14 && key==106)eq_default(&c);
    else if(row==15 && key==106){STATE->open=0;return 1;}
    STATE->pending=c;
    return 1;
}

void *memcpy(void *dest,const void *source,size_t size) {
    volatile unsigned char *d=dest;
    const volatile unsigned char *s=source;
    for(size_t i=0;i<size;i++)d[i]=s[i];
    return dest;
}
void *memset(void *dest,int value,size_t size) {
    volatile unsigned char *d=dest;
    for(size_t i=0;i<size;i++)d[i]=(unsigned char)value;
    return dest;
}
