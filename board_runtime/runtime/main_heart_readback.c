/* Fixed bounded unified-main transport. No mapping, allocation, initialization,
 * callbacks in production, heart arithmetic, or automatic retry. Only the
 * explicit hm_transact_sample entry may issue one SAMPLE and its matched ACK.
 * Adapted from this project's retained history100_readback.c transport.
 */
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stddef.h>
#include <math.h>
#ifdef _WIN32
#include <windows.h>
#define API __declspec(dllexport)
#else
#include <time.h>
#define API __attribute__((visibility("default")))
#endif
#ifndef HMAIN_ARM_MMIO
#define HMAIN_ARM_MMIO 0
#endif
#if HMAIN_ARM_MMIO && (!defined(__arm__) || !defined(__ARM_ARCH) || __ARM_ARCH<7 || UINTPTR_MAX!=UINT32_MAX)
#error Physical main transport requires original ARMv7/32bit pointers
#endif
#if HMAIN_ARM_MMIO && defined(HMAIN_TEST)
#error Test hooks are forbidden in physical MMIO builds
#endif
#ifdef HMAIN_TEST
static double (*test_clock)(void);
static uint32_t test_ram_completions;
API void hm_test_clock(double (*fn)(void)) { test_clock=fn; }
API void hm_test_ram_completions(uint32_t enabled) { test_ram_completions=enabled; }
#endif
API uint32_t hm_abi(void) { return 0x484d5203u; }
API uint32_t hm_arm_mmio_capable(void) { return HMAIN_ARM_MMIO; }
API double hm_now(void) {
#ifdef HMAIN_TEST
    if(test_clock) return test_clock();
#endif
#ifdef _WIN32
    return (double)GetTickCount64()/1000.;
#else
    struct timespec ts;
    uint64_t ns;
    if(clock_gettime(CLOCK_MONOTONIC,&ts)) return -1.;
    ns=(uint64_t)ts.tv_sec*1000000000ull+(uint64_t)ts.tv_nsec;
    return (double)ns/1000000000.;
#endif
}
static int disjoint(uintptr_t a,size_t na,uintptr_t b,size_t nb) {
    return a<=UINTPTR_MAX-na && b<=UINTPTR_MAX-nb && !(a<b+nb && b<a+na);
}
static int expired(double deadline) {
    double now=hm_now();
    if(!isfinite(now) || now<0.) return 3;
    return now>=deadline ? 1 : 0;
}
API int hm_read_snapshot(const volatile uint32_t *mapped,size_t capacity,
                        uint32_t *output,size_t output_capacity,double deadline,uint32_t *completed) {
    uintptr_t a=(uintptr_t)mapped,b=(uintptr_t)output,c=(uintptr_t)completed;
    uint32_t i,index,position;int rc;
    if(!mapped || !output || !completed || capacity!=16384 || output_capacity!=174 ||
        (a&3u) || (b&3u) || (c&3u) || !isfinite(deadline) ||
        !disjoint(a,65536,b,696) || !disjoint(a,65536,c,4) || !disjoint(b,696,c,4)) return 2;
    *completed=0;
    for(i=0;i<174;++i) {
        if((rc=expired(deadline))) return rc;
        if(i<22) index=40+i; /* exact22-word active identity echo @0xa0 */
        else if(i<54) index=1024+384+i-22; /*16 scalar u64 snapshot words */
        else {
            position=i-54;
            index=1024+2*(41+32*(position/30))+position%30;
        }
#if HMAIN_ARM_MMIO
        __asm__ __volatile__("dmb sy" ::: "memory");
#endif
        output[i]=mapped[index];
#if HMAIN_ARM_MMIO
        __asm__ __volatile__("dsb sy" ::: "memory");
#endif
        *completed=i+1;
        if((rc=expired(deadline))) return rc;
    }
    return 0;
}

/* Format decoding only, not a PPG/NLMS/SQI implementation. The already
 * copied binary64 words are reinterpreted, never recomputed or rounded. */
struct hm_branch {
    double filtered,bpm,ibis[5],position;
    uint64_t index,last_index,accepted;
    uint32_t count,has_last,has_bpm,peak;
};
struct hm_result {
    double wave[5];
    uint32_t status;
    int32_t candidate,output;
    uint32_t reason,checked,protection;
    struct hm_branch branches[4];
};
API uint32_t hm_result_bytes(void) { return (uint32_t)sizeof(struct hm_result); }
API uint32_t hm_branch_bytes(void) { return (uint32_t)sizeof(struct hm_branch); }
static uint64_t bits64(const uint32_t *p) { return (uint64_t)p[0] | (uint64_t)p[1]<<32; }
static double double64(const uint32_t *p) { union {uint64_t u;double d;} v;v.u=bits64(p);return v.d; }
API int hm_decode_snapshot(const uint32_t *words,size_t count,const uint32_t *expected,size_t expected_count,
                          uint32_t valid,struct hm_result *result,size_t result_bytes) {
    uintptr_t a=(uintptr_t)words,b=(uintptr_t)expected,c=(uintptr_t)result;
    uint64_t status,candidate,output,reason,checked,protection,n,last,bpm,peak;
    const uint32_t *p;uint32_t i,j;double value;
    if(!words || !expected || !result || count!=174 || expected_count!=22 || valid>1 ||
        result_bytes!=sizeof(struct hm_result) || (a&3u) || (b&3u) || (c&7u) ||
        !disjoint(a,696,c,sizeof(struct hm_result)) || !disjoint(b,88,c,sizeof(struct hm_result))) return 2;
    for(i=0;i<22;++i) if(words[i]!=expected[i]) return 4;
    *result=(struct hm_result){0};
    for(i=0;i<5;++i) {
        value=double64(words+22+2*i);
        if(!isfinite(value)) return 6;
        result->wave[i]=value;
    }
    status=bits64(words+32);candidate=bits64(words+34);output=bits64(words+36);
    if(status>15 || (status&8) || (status&1)!=valid ||
        candidate!=(uint64_t)(int64_t)(int32_t)candidate || output!=(uint64_t)(int64_t)(int32_t)output ||
        result->wave[2]!=(double)(int32_t)candidate/65536.) return 5;
    reason=bits64(words+48);checked=bits64(words+50);protection=bits64(words+52);
    value=result->wave[4];
    if(reason>=14 || checked>1 || protection>1 ||
        !(value==0. || value==.2 || value==.4 || value==.6 || value==.8 || value==1.)) return 5;
    result->status=(uint32_t)status;result->candidate=(int32_t)candidate;result->output=(int32_t)output;
    result->reason=(uint32_t)reason;result->checked=(uint32_t)checked;result->protection=(uint32_t)protection;
    if(!valid) return 0;
    for(i=0;i<4;++i) {
        struct hm_branch *v=&result->branches[i];p=words+54+30*i;
        n=bits64(p+10);last=bits64(p+6);bpm=bits64(p+24);peak=bits64(p+26);
        if(n>5 || last>1 || bpm>1 || peak>1) return 5;
        v->count=(uint32_t)n;v->has_last=(uint32_t)last;v->has_bpm=(uint32_t)bpm;v->peak=(uint32_t)peak;
        v->index=bits64(p);v->last_index=bits64(p+2);v->accepted=bits64(p+8);
        v->filtered=double64(p+28);
        if(!isfinite(v->filtered)) return 6;
        for(j=0;j<n;++j) {v->ibis[j]=double64(p+12+2*j);if(!isfinite(v->ibis[j])) return 6;}
        if(last) {v->position=double64(p+4);if(!isfinite(v->position)) return 6;}
        if(bpm) {v->bpm=double64(p+22);if(!isfinite(v->bpm)) return 6;}
    }
    return 0;
}

static int read_reg(const volatile uint32_t *mapped,uint32_t index,double deadline,uint32_t *value) {
    int rc=expired(deadline);if(rc) return rc;
#if HMAIN_ARM_MMIO
    __asm__ __volatile__("dmb sy" ::: "memory");
#endif
    *value=mapped[index];
#if HMAIN_ARM_MMIO
    __asm__ __volatile__("dsb sy" ::: "memory");
#endif
    return expired(deadline);
}
static int write_reg(volatile uint32_t *mapped,uint32_t index,uint32_t value,double deadline) {
    int rc=expired(deadline);if(rc) return rc;
#if HMAIN_ARM_MMIO
    __asm__ __volatile__("dmb sy" ::: "memory");
#endif
    mapped[index]=value;
#if HMAIN_ARM_MMIO
    __asm__ __volatile__("dsb sy" ::: "memory");
#endif
#ifdef HMAIN_TEST
    /* C-only RAM completion in the nonphysical test binary. This code and
     * its selector symbol are absent from every physical ARM build. */
    if(test_ram_completions && index==2) {
        uint32_t i;
        if(value==2) {mapped[3]|=2;mapped[7]=2;for(i=0;i<22;++i) mapped[40+i]=mapped[16+i];}
        else if(value==4) mapped[3]&=~2u;
    }
#endif
    return expired(deadline);
}
API int hm_transact_sample(volatile uint32_t *mapped,size_t capacity,const uint32_t *expected,size_t expected_count,
                          uint32_t valid,struct hm_result *result,size_t result_bytes,double deadline,uint32_t *phase) {
    uintptr_t a=(uintptr_t)mapped,b=(uintptr_t)expected,c=(uintptr_t)result,d=(uintptr_t)phase;
    uint32_t words[174],done=0,i,status,epoch,command;int rc;
    if(!mapped || !expected || !result || !phase || capacity!=16384 || expected_count!=22 || valid>1 ||
        result_bytes!=sizeof(struct hm_result) || (a&3u) || (b&3u) || (c&7u) || (d&3u) || !isfinite(deadline) ||
        !disjoint(a,65536,b,88) || !disjoint(a,65536,c,sizeof(struct hm_result)) || !disjoint(a,65536,d,4) ||
        !disjoint(b,88,c,sizeof(struct hm_result)) || !disjoint(b,88,d,4) || !disjoint(c,sizeof(struct hm_result),d,4)) return 2;
    *phase=1;
    for(i=0;i<22;++i) if((rc=write_reg(mapped,16+i,expected[i],deadline))) return rc;
    *phase=2;if((rc=write_reg(mapped,2,2,deadline))) return rc;
    *phase=3;
    for(;;) {
        if((rc=read_reg(mapped,3,deadline,&status))) return rc;
        if(status&12) return 7;
        if(!(status&1)) break;
    }
    if(!(status&2) || !(status&64) || (status&48)!=48) return 5;
    if((rc=read_reg(mapped,6,deadline,&epoch)) || (rc=read_reg(mapped,7,deadline,&command))) return rc;
    if(epoch!=expected[10] || command!=2) return 4;
    *phase=4;if((rc=hm_read_snapshot(mapped,16384,words,174,deadline,&done))) return rc;
    if(done!=174) return 3;
    *phase=5;if((rc=hm_decode_snapshot(words,174,expected,22,valid,result,result_bytes))) return rc;
    if((rc=expired(deadline))) return rc;
    *phase=6;if((rc=write_reg(mapped,2,4,deadline))) return rc;
    *phase=7;if((rc=read_reg(mapped,3,deadline,&status))) return rc;
    if(status&7) return 8;
    return expired(deadline);
}
