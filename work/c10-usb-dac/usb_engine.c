#include "stock_abi.h"
#include "descriptors.h"
#include "feedback.h"
#define OUT_REQUESTS 8
#define PACKET_BYTES 200
#define RING_FRAMES 16384u
#define BLOCK_FRAMES 256u
#define FRAME_BYTES 4u
typedef struct {
 void *audio,*gadget;ep *out,*feedback_ep;request *rx[OUT_REQUESTS],*fb;
 unsigned char *ring,*scratch;dac_descriptors fs,hs;
 dac_feedback clock;
 volatile uint32_t generation,pcm_generation,producer,consumer,running;
 unsigned high_speed,enabled_out,enabled_feedback,bound,work_active;
 unsigned error,rx_packets,feedback_packets,xruns,primed,prefill;
} engine;
static engine state;
void c10_work(void *work);
void c10_disable(void *audio);
static void barrier(void){__asm__ volatile("sync":::"memory");}
static void fail(unsigned code){
 if(!state.error){state.error=code;printk("<3>C10_USB72 error=%u rx=%u feedback=%u\n",code,state.rx_packets,state.feedback_packets);}
 state.running=0;barrier();schedule_work((unsigned char *)state.audio+0xa0);
}
static int current_speed(void){return U32(state.gadget,16)==3u;}
static void *pcm(void){return PTR(state.audio,0x64);}
static void *runtime(void){void *s=pcm();return s?PTR(s,0x70):0;}
static int kernel_pcm_write(const void *buf,unsigned frames){
 void *sub=pcm();uint32_t flags=U32(sub,0xa4),old=kernel_limit_get();
 /* Verified original kernel8025eec0: f_flags+0xa4 bit7 selects nonblocking. */
 U32(sub,0xa4)=flags|0x80u;kernel_limit_set(0);
 int r=snd_pcm_lib_write(sub,buf,frames);kernel_limit_set(old);U32(sub,0xa4)=flags;return r;
}
static void feedback_fill(void){
 uint32_t q=6u<<16;void *r=runtime();unsigned running=0;uint32_t hw=0,boundary=0;
 if(r){void *status=PTR(r,0x94);if(status){running=U32(status,0)==PCM_RUNNING && state.pcm_generation==state.generation;hw=U32(status,8);boundary=U32(r,0x78);}}
 void *ops=PTR(state.gadget,0);int (*get_frame)(void *)=ops?PTR(ops,0):0;
 int frame=get_frame?get_frame(state.gadget):-1;
 if(frame>=0)q=dac_feedback_tick(&state.clock,running,hw,boundary,(unsigned)frame);
 dac_feedback_encode(q,state.high_speed,state.fb->buf);
 state.fb->length=state.high_speed?4:3;
}
static void feedback_complete(ep *endpoint,request *req){
 if(!state.running)return;
 if(req->status){fail(14);return;}
 state.feedback_packets++;feedback_fill();
 int r=endpoint->ops->queue(endpoint,req,GFP_ATOMIC);if(r)fail(10);
}
static void out_complete(ep *endpoint,request *req){
 if(!state.running)return;
 if(req->status){fail(15);return;}
 unsigned bytes=req->actual;
 if(bytes>PACKET_BYTES || bytes%FRAME_BYTES){fail(11);return;}
 unsigned frames=bytes/FRAME_BYTES,used=state.producer-state.consumer;
 if(used>RING_FRAMES || frames>RING_FRAMES-used){fail(12);return;}
 unsigned char *source=req->buf;uint32_t producer=state.producer;
 for(unsigned i=0;i<bytes;i++)state.ring[((producer*FRAME_BYTES)+i)%(RING_FRAMES*FRAME_BYTES)]=source[i];
 barrier();state.producer=producer+frames;dac_feedback_receive(&state.clock,frames);state.rx_packets++;
 schedule_work((unsigned char *)state.audio+0xa0);
 int r=endpoint->ops->queue(endpoint,req,GFP_ATOMIC);if(r)fail(13);
}
static void disable_endpoints(void){
 state.running=0;barrier();
 if(state.enabled_feedback){state.enabled_feedback=0;state.feedback_ep->ops->disable(state.feedback_ep);}
 if(state.enabled_out){state.enabled_out=0;state.out->ops->disable(state.out);}
}
static void free_request(ep *endpoint,request **req){
 if(*req){kfree((*req)->buf);(*req)->buf=0;endpoint->ops->free(endpoint,*req);*req=0;}
}
static void release_allocations(void){
 free_request(state.feedback_ep,&state.fb);
 for(unsigned i=0;i<OUT_REQUESTS;i++)free_request(state.out,&state.rx[i]);
 kfree(state.scratch);state.scratch=0;kfree(state.ring);state.ring=0;
}
static request *allocate_request(ep *endpoint,unsigned bytes,void (*complete)(ep *,request *)){
 request *req=endpoint->ops->alloc(endpoint,GFP_KERNEL_ZERO);if(!req)return 0;
 req->buf=__kmalloc(bytes,GFP_KERNEL_ZERO);
 if(!req->buf){endpoint->ops->free(endpoint,req);return 0;}
 req->length=bytes;req->flags=0;req->complete=complete;req->context=&state;return req;
}
int c10_bind(void *config,void *audio){
 if(state.bound)return -16;
 int r=stock_f_audio_bind(config,audio);if(r)return r;
 state.audio=audio;state.gadget=PTR(PTR(config,0x1c),0);state.out=PTR(audio,0x94);
 void **oldfs=PTR(audio,8),**oldhs=PTR(audio,12);void **old=oldhs?oldhs:oldfs;
 unsigned ac=255,as=255,epout=0;
 if(old)for(unsigned i=0;i<24 && old[i];i++){
  const unsigned char *d=old[i];if(d[1]==4 && d[5]==1){if(d[6]==1)ac=d[2];else if(d[6]==2)as=d[2];}
  if(d[1]==5 && !(d[2]&0x80))epout=d[2];
 }
 if(!state.gadget || !state.out || ac==255 || as==255 || !epout){r=-22;goto failed;}
 /* Autoconfiguration requires an unclaimed, real IN endpoint. */
 if(dac_descriptors_init(&state.hs,1,ac,as,epout,0x81)){r=-22;goto failed;}
 state.hs.feedback[2]=0x80;
 state.feedback_ep=usb_ep_autoconfig(state.gadget,state.hs.feedback);
 if(!state.feedback_ep){r=-19;goto failed;}
 state.feedback_ep->driver_data=audio;
 unsigned epin=state.hs.feedback[2];
 if(dac_descriptors_init(&state.fs,0,ac,as,epout,epin) || dac_descriptors_init(&state.hs,1,ac,as,epout,epin)){r=-22;goto failed;}
 void **fs=usb_copy_descriptors((const void **)state.fs.list);if(!fs){r=-12;goto failed;}
 void **hs=usb_copy_descriptors((const void **)state.hs.list);if(!hs){kfree(fs);r=-12;goto failed;}
 PTR(audio,8)=fs;PTR(audio,12)=hs;kfree(oldfs);kfree(oldhs);oldfs=oldhs=0;
 state.ring=__kmalloc(RING_FRAMES*FRAME_BYTES,GFP_KERNEL_ZERO);
 state.scratch=__kmalloc(BLOCK_FRAMES*FRAME_BYTES,GFP_KERNEL_ZERO);
 if(!state.ring || !state.scratch){r=-12;goto failed;}
 for(unsigned i=0;i<OUT_REQUESTS;i++){state.rx[i]=allocate_request(state.out,PACKET_BYTES,out_complete);if(!state.rx[i]){r=-12;goto failed;}}
 state.fb=allocate_request(state.feedback_ep,4,feedback_complete);if(!state.fb){r=-12;goto failed;}
 state.bound=1;printk("<6>C10_USB72 bind OUT=%u feedback=%u PCM=48000/16/2\n",epout,epin);return 0;
failed:
 release_allocations();if(state.feedback_ep)state.feedback_ep->driver_data=0;
 if(state.out)state.out->driver_data=0;
 /* Failed bind is followed by the factory caller's gaudio_cleanup+free(audio).
  * It does not call unbind, so release descriptor copies here. */
 if(oldfs || oldhs){kfree(oldfs);kfree(oldhs);}else{kfree(PTR(audio,8));kfree(PTR(audio,12));}
 PTR(audio,8)=PTR(audio,12)=0;state.audio=0;state.gadget=0;state.out=state.feedback_ep=0;return r;
}
int c10_set_alt(void *audio,unsigned interface,unsigned alt){
 if(!state.bound || state.audio!=audio)return -19;
 if(interface!=state.hs.alt1[2])return alt?-22:0;
 if(alt>1)return -22;
 if(!alt){c10_disable(audio);return 0;}
 if(state.running)return 0;
 disable_endpoints();
 uint32_t flags=irq_save();state.generation++;state.pcm_generation=0;state.producer=state.consumer=0;
 state.error=state.rx_packets=state.feedback_packets=state.xruns=state.primed=0;dac_feedback_reset(&state.clock);irq_restore(flags);
 state.high_speed=(unsigned)current_speed();dac_descriptors *d=state.high_speed?&state.hs:&state.fs;
 PTR(audio,0x98)=d->out;
 int r=state.out->ops->enable(state.out,d->out);if(r)return r;state.enabled_out=1;
 r=state.feedback_ep->ops->enable(state.feedback_ep,d->feedback);if(r){disable_endpoints();return r;}state.enabled_feedback=1;
 state.running=1;barrier();feedback_fill();
 r=state.feedback_ep->ops->queue(state.feedback_ep,state.fb,GFP_ATOMIC);
 if(r){disable_endpoints();return r;}
 for(unsigned i=0;i<OUT_REQUESTS;i++){
  state.rx[i]->length=PACKET_BYTES;r=state.out->ops->queue(state.out,state.rx[i],GFP_ATOMIC);
  if(r){disable_endpoints();schedule_work((unsigned char *)audio+0xa0);return r;}
 }
 schedule_work((unsigned char *)audio+0xa0);
 printk("<6>C10_USB72 start generation=%u highspeed=%u\n",state.generation,state.high_speed);return 0;
}
void c10_disable(void *audio){
 if(state.audio!=audio || !state.bound)return;
 disable_endpoints();schedule_work((unsigned char *)audio+0xa0);
 printk("<6>C10_USB72 stop generation=%u rx=%u feedback=%u xrun=%u error=%u\n",state.generation,state.rx_packets,state.feedback_packets,state.xruns,state.error);
}
void c10_work(void *work){
 if(!state.bound || work!=(unsigned char *)state.audio+0xa0)return;
 state.work_active=1;
 for(;;){
  uint32_t generation=state.generation;
  if(!state.running){
   snd_pcm_kernel_ioctl(pcm(),PCM_DROP,0);
   uint32_t f=irq_save();
   if(!state.running && state.generation==generation){state.pcm_generation=0;state.consumer=state.producer;irq_restore(f);break;}
   irq_restore(f);continue;
  }
  if(state.pcm_generation!=generation){
   int r=snd_pcm_kernel_ioctl(pcm(),PCM_DROP,0);if(!r)r=snd_pcm_kernel_ioctl(pcm(),PCM_PREPARE,0);
   if(r){state.error=20;state.running=0;continue;}
   if(state.generation!=generation)continue;
   state.pcm_generation=generation;state.primed=0;
   void *rtime=runtime();unsigned period=rtime?U32(rtime,0x38):0;
   if(!period || period>8192){state.error=23;state.running=0;continue;}
   state.prefill=period*2;if(state.prefill<2048)state.prefill=2048;if(state.prefill>8192)state.prefill=8192;
  }
  uint32_t flags=irq_save();
  if(!state.running || state.generation!=generation){irq_restore(flags);continue;}
  uint32_t consumer=state.consumer,frames=state.producer-consumer;
  if(frames>RING_FRAMES){irq_restore(flags);state.error=21;state.running=0;continue;}
  if(!state.primed){if(frames<state.prefill){irq_restore(flags);break;}state.primed=1;}
  if(frames>BLOCK_FRAMES)frames=BLOCK_FRAMES;
  for(unsigned i=0;i<frames*FRAME_BYTES;i++)state.scratch[i]=state.ring[(consumer*FRAME_BYTES+i)%(RING_FRAMES*FRAME_BYTES)];
  irq_restore(flags);
  if(!frames)break;
  unsigned written=0;int backpressure=0;
  while(written<frames && state.running && state.generation==generation){
   int n=kernel_pcm_write(state.scratch+written*FRAME_BYTES,frames-written);
   if(state.generation!=generation || !state.running)break;
   if(n==-11){backpressure=1;break;}
   if(n<=0 || (unsigned)n>frames-written){state.xruns++;state.error=22;state.running=0;break;}
   written+=(unsigned)n;
  }
  flags=irq_save();if(state.generation==generation)state.consumer=consumer+written;irq_restore(flags);
  if(backpressure)break; /* next OUT packet schedules a retry; never busy-spin */
 }
 state.work_active=0;
}
void c10_unbind(void *config,void *audio){
 if(state.audio==audio){
  disable_endpoints();
  /* unbind is process context (stock cleanup closes files here too). Drop
   * first so even an already-running old write cannot pin module removal. */
  snd_pcm_kernel_ioctl(pcm(),PCM_DROP,0);cancel_work_sync((unsigned char *)audio+0xa0);
  state.bound=0;release_allocations();if(state.feedback_ep)state.feedback_ep->driver_data=0;
  if(state.out)state.out->driver_data=0;
  state.feedback_ep=0;state.audio=0;state.gadget=0;state.out=0;
 }
 stock_f_audio_unbind(config,audio);
}
void *memcpy(void *dest,const void *source,size_t n){unsigned char *d=dest;const unsigned char *s=source;for(size_t i=0;i<n;i++)d[i]=s[i];return dest;}
void *memset(void *dest,int v,size_t n){unsigned char *d=dest;for(size_t i=0;i<n;i++)d[i]=(unsigned char)v;return dest;}
