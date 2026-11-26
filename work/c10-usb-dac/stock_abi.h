#ifndef C10_STOCK_ABI_H
#define C10_STOCK_ABI_H
#include <stdint.h>
#include <stddef.h>
typedef struct usb_ep ep;
typedef struct usb_request request;
typedef struct {int (*enable)(ep *,const void *);int (*disable)(ep *);request *(*alloc)(ep *,unsigned);void (*free)(ep *,request *);int (*queue)(ep *,request *,unsigned);int (*dequeue)(ep *,request *);} ep_ops;
struct usb_ep {void *driver_data;const char *name;const ep_ops *ops;uint32_t list[2];unsigned maxpacket;};
struct usb_request {void *buf;unsigned length;uint32_t dma,flags;void (*complete)(ep *,request *);void *context;uint32_t list[2];int status;unsigned actual;};
#if UINTPTR_MAX==0xffffffffu
_Static_assert(offsetof(ep,ops)==8,"original ep ops");
_Static_assert(offsetof(request,complete)==16 && offsetof(request,status)==32 && offsetof(request,actual)==36,"original request layout");
#endif
#define U32(p,o) (*(volatile uint32_t *)((unsigned char *)(p)+(o)))
#define PTR(p,o) (*(void **)((unsigned char *)(p)+(o)))
#define GFP_KERNEL_ZERO 0x80d0u
#define GFP_ATOMIC 0x20u
#define PCM_DROP 0x20004143u
#define PCM_PREPARE 0x20004140u
#define PCM_RUNNING 3u
extern void *__kmalloc(unsigned,unsigned);
extern void kfree(void *);
extern int printk(const char *,...);
extern int schedule_work(void *);
extern int cancel_work_sync(void *);
extern int snd_pcm_kernel_ioctl(void *,unsigned,void *);
extern int snd_pcm_lib_write(void *,const void *,unsigned);
extern ep *usb_ep_autoconfig(void *,void *);
extern void **usb_copy_descriptors(const void **);
extern int stock_f_audio_bind(void *,void *);
extern void stock_f_audio_unbind(void *,void *);
static inline uint32_t irq_save(void){
 uint32_t old,next;__asm__ volatile("mfc0 %0,$12\n\tnop":"=r"(old));next=old&~1u;
 __asm__ volatile("mtc0 %0,$12\n\tnop\n\tnop\n\tnop"::"r"(next):"memory");return old;
}
static inline void irq_restore(uint32_t old){__asm__ volatile("mtc0 %0,$12\n\tnop\n\tnop\n\tnop"::"r"(old):"memory");}
static inline uint32_t kernel_limit_get(void){uintptr_t gp;__asm__ volatile("move %0,$gp":"=r"(gp));return U32((void *)gp,24);}
static inline void kernel_limit_set(uint32_t n){uintptr_t gp;__asm__ volatile("move %0,$gp":"=r"(gp));U32((void *)gp,24)=n;__asm__ volatile("sync":::"memory");}
#endif
