/* Included after launch logging; saved configuration and preview are distinct.
 * The cfg lock protects copies/epochs only. Never perform IO under that lock.
 * A second trylock serializes short nonblocking FIFO writes, not popen/fgets.
 */
static int config_equal(const eq_config *a,const eq_config *b){
    if(a->enabled!=b->enabled || a->preset!=b->preset)return 0;
    for(int i=0;i<EQ_BANDS;i++)if(a->gain[i]!=b->gain[i])return 0;
    return 1;
}
static void effective_locked(eq_config *c){
    *c=STATE->preview_on?STATE->preview:STATE->active[STATE->active_slot&1u];
}
static int contains(const char *s,const char *needle){
    for(;*s;s++){unsigned n=0;while(needle[n] && s[n]==needle[n])n++;if(!needle[n])return 1;}
    return 0;
}
static int exact(const char *a,const char *b){while(*a&&*a==*b){a++;b++;}return *a==*b;}

/* 0=complete, 1=retry (EAGAIN/no reader), -1=unsafe descriptor/short write.
 * Kernel PIPE_BUF on this machine is >=512. No stdio buffer and no O_RDWR.
 */
static int fifo_packet(const char *packet,unsigned size,unsigned epoch,unsigned stream){
    if(!size || size>512)return -1;
    int fd=orig_open("/tmp/cmd",O_WRONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC,0);
    if(fd<0)return 1;
    unsigned long long statbuf[16];
    int result=1;
    if(orig_fstat64(fd,statbuf)<0 || (((unsigned *)statbuf)[6]&0170000u)!=0010000u)result=-1;
    else {
        lock_state();
        int current=STATE->epoch==epoch && STATE->stream==stream &&
            WORD(0x444cd8u)==stream && WORD(0x444440u)==1u;
        unlock_state();
        if(current){int n=orig_write(fd,packet,size);result=n==(int)size?0:n<0?1:-1;}
    }
    orig_close(fd);
    return result;
}

void eq_live_poll(unsigned now){
    if(STATE->initialized!=MAGIC)return;
    STATE->now=now;
    if(__sync_lock_test_and_set(&STATE->live_lock,1u))return;
    eq_config desired,applied;unsigned epoch,stream,phase,attempt,has_pair;int volume;
    lock_state();
    epoch=STATE->epoch;stream=STATE->stream;phase=STATE->phase;
    effective_locked(&desired);applied=STATE->applied;volume=STATE->applied_volume;
    attempt=STATE->attempted;has_pair=STATE->has_pair;
    int dirty=STATE->dirty;
    unsigned start=STATE->started;
    unlock_state();
    if(!stream || WORD(0x444cd8u)!=stream || !eq_valid(&desired))goto done;
    if(WORD(0x444440u)!=1u){
        /* Stock stdout reader sleeps while paused. Keep its behavior intact,
         * coalesce edits, and do not let a paused handshake time out. */
        lock_state();if(STATE->epoch==epoch && STATE->phase==1)STATE->started=now;unlock_state();
        goto done;
    }
    if(phase==1){
        if((unsigned)(now-start)<2000u)goto done;
        lock_state();if(STATE->epoch==epoch && STATE->phase==1){STATE->phase=3;STATE->status=4;}unlock_state();
        phase=3;
    }
    if(phase==4 || (!dirty && phase!=3))goto done;
    char packet[512];int size;
    if(phase==3){
        /* Best-effort flat/unity recovery, then disable live for this epoch.
         * Never issue positive compensation after an unconfirmed install. */
        static const char recover[]="\npausing_keep_force af_cmdline equalizer 0:0:0:0:0:0:0:0:0:0\npausing_keep_force af_cmdline volume 0.0:0:0\n";
        int r=fifo_packet(recover,sizeof(recover)-1,epoch,stream);
        lock_state();if(STATE->epoch==epoch && r!=1){STATE->phase=4;STATE->status=4;}unlock_state();
        goto done;
    }
    if(phase==0){
        if(attempt)goto done;
        size=eq_live_change(&applied,volume,&desired,packet,sizeof(packet));
        if(!size && !(desired.enabled && !has_pair)){
            lock_state();eq_config current;effective_locked(&current);
            if(STATE->epoch==epoch)STATE->dirty=!config_equal(&current,&desired);
            unlock_state();goto done;
        }
        size=eq_live_install(!has_pair,packet,sizeof(packet));
        if(size<=0)goto done;
        lock_state();
        if(STATE->epoch!=epoch){unlock_state();goto done;}
        STATE->phase=1;STATE->attempted=1;STATE->install_error=0;STATE->started=now;
        unlock_state();
        int r=fifo_packet(packet,(unsigned)size,epoch,stream);
        if(!r){diag_write("live=install\n",13);diag_write(packet,(unsigned)size);}
        lock_state();
        if(STATE->epoch==epoch && r){
            if(r==1){STATE->phase=0;STATE->attempted=0;}
            else{STATE->phase=3;STATE->status=4;}
        }
        unlock_state();goto done;
    }
    size=eq_live_change(&applied,volume,&desired,packet,sizeof(packet));
    if(size<0)goto done;
    int r=size?fifo_packet(packet,(unsigned)size,epoch,stream):0;
    if(!r && size){diag_write("live=change\n",12);diag_write(packet,(unsigned)size);}
    lock_state();
    if(STATE->epoch==epoch && STATE->phase==2){
        if(!r){
            STATE->applied=desired;STATE->applied_volume=desired.enabled?eq_volume_tenths(&desired):0;
            eq_config current;effective_locked(&current);STATE->dirty=!config_equal(&current,&desired);
        }else if(r<0){STATE->phase=3;STATE->status=4;}
    }
    unlock_state();
done:
    __sync_lock_release(&STATE->live_lock);
}

static void preview_request(const eq_config *c,int on){
    lock_state();STATE->preview=*c;STATE->preview_on=(unsigned)on;STATE->dirty=1;unlock_state();
    eq_live_poll(STATE->now);
}
static void cancel_preview(void){
    eq_config c;snapshot(&c);STATE->open=0;preview_request(&c,0);
}
static void *live_launch(const eq_config *c,const char *cmd,const char *mode,unsigned size,int filtered,int observable){
    lock_state();unsigned epoch=STATE->epoch+1;STATE->epoch=epoch;
    STATE->stream=0;STATE->phase=observable?0:4;STATE->attempted=0;
    eq_config current;effective_locked(&current);STATE->dirty=!config_equal(&current,c);
    STATE->applied=*c;STATE->applied_volume=filtered?eq_volume_tenths(c):0;
    STATE->has_pair=(unsigned)filtered;STATE->install_error=0;
    unlock_state();
    void *result=launch_logged(c,cmd,mode,size);
    lock_state();if(STATE->epoch==epoch)STATE->stream=(unsigned)(uintptr_t)result;unlock_state();
    return result;
}
static void live_line(char *buffer,unsigned epoch,unsigned stream){
    int fence=exact(buffer,"ANS_pause=yes\n") || exact(buffer,"ANS_pause=no\n");
    int error=contains(buffer,"Unable to find audio filter") ||
             contains(buffer,"Could not find audio filter") ||
             contains(buffer,"Couldn't find audio filter") ||
             contains(buffer,"not found") ||
             contains(buffer,"Couldn't create or open") ||
             contains(buffer,"Could not allocate memory") ||
             contains(buffer,"Reinitialization did not work") ||
             contains(buffer,"Automatic filter insertion disabled") ||
             contains(buffer,"Unable to setup filter") || contains(buffer,"Unable to correct audio");
    lock_state();
    if(STATE->epoch==epoch && STATE->stream==stream){
        if(STATE->phase==1){
            if(fence){
                if(STATE->install_error){STATE->phase=3;STATE->status=4;}
                else{eq_config flat;eq_default(&flat);STATE->applied=flat;
                    STATE->applied_volume=-2000;STATE->phase=2;STATE->has_pair=1;STATE->dirty=1;}
            }else if(error)STATE->install_error=1;
        }else if(STATE->phase==2 && error){STATE->phase=3;STATE->status=4;}
    }
    unlock_state();
    if(fence)buffer[0]=0; /* internal response never reaches stock line parser */
}
