/* Candidate only: bound one unchanged native call to a temporary thread policy.
 * No MMIO, deadline adjustment, retry, affinity, algorithm, or GC changes here. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
#ifdef HS_TEST
#define API __declspec(dllexport)
static int test_policy, test_priority, test_gets, test_sets;
static int test_get_failure, test_enter_failure, test_restore_failure;
API void hs_test_reset(int get_failure, int enter_failure, int restore_failure,
                       int policy, int priority) {
    test_policy=policy; test_priority=priority; test_gets=test_sets=0;
    test_get_failure=get_failure; test_enter_failure=enter_failure;
    test_restore_failure=restore_failure;
}
API int hs_test_state(int field) {
    return field==0?test_policy:field==1?test_priority:field==2?test_gets:test_sets;
}
static int get_policy(int *policy,int *priority) {
    ++test_gets;
    if(test_gets==test_get_failure)return EINVAL;
    *policy=test_policy; *priority=test_priority; return 0;
}
static int set_policy(int policy,int priority) {
    ++test_sets;
    if((test_sets==1&&test_enter_failure)||(test_sets==2&&test_restore_failure))return EPERM;
    test_policy=policy; test_priority=priority; return 0;
}
#define NORMAL_POLICY 0
#define REALTIME_POLICY 1
static int minimum_priority(void) { return 1; }
#else
#if !defined(__linux__)
#error Production helper requires Linux pthread scheduling
#endif
#include <pthread.h>
#include <sched.h>
#define API __attribute__((visibility("default")))
#define NORMAL_POLICY SCHED_OTHER
#define REALTIME_POLICY SCHED_FIFO
static int get_policy(int *policy,int *priority) {
    struct sched_param p;
    int err=pthread_getschedparam(pthread_self(),policy,&p);
    if(!err)*priority=p.sched_priority;
    return err;
}
static int set_policy(int policy,int priority) {
    struct sched_param p;
    memset(&p,0,sizeof(p)); p.sched_priority=priority;
    return pthread_setschedparam(pthread_self(),policy,&p);
}
static int minimum_priority(void) { return sched_get_priority_min(SCHED_FIFO); }
#endif

typedef struct {
    int32_t abi, stage, get_error, enter_error, restore_error, verify_error;
    int32_t policy_before, priority_before, policy_after, priority_after;
    int32_t delegated, primary_code, return_code, priority_requested, reserved0, reserved1;
} Record;
enum { BAD_ARGUMENT=200, POLICY_FAILURE=201, RESTORE_FAILURE=202 };
API uint32_t hs_record_bytes(void) { return (uint32_t)sizeof(Record); }
API uint32_t hs_abi(void) { return 0x48534701; }
static int overlaps(const void *a,size_t na,const void *b,size_t nb) {
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(!a||!b||!na||!nb)return 0;
    if(x>UINTPTR_MAX-na||y>UINTPTR_MAX-nb)return 1;
    return x<y+nb&&y<x+na;
}
static int begin(Record *r) {
    r->stage=1;
    r->get_error=get_policy(&r->policy_before,&r->priority_before);
    if(r->get_error||r->policy_before!=NORMAL_POLICY||r->priority_before!=0)
        return r->return_code=POLICY_FAILURE;
    r->priority_requested=minimum_priority();
    if(r->priority_requested<1)return r->return_code=POLICY_FAILURE;
    r->enter_error=set_policy(REALTIME_POLICY,r->priority_requested);
    if(r->enter_error)return r->return_code=POLICY_FAILURE;
    r->stage=2; return 0;
}
static int finish(Record *r,int primary) {
    r->primary_code=primary; r->stage=3;
    r->restore_error=set_policy(r->policy_before,r->priority_before);
    r->verify_error=get_policy(&r->policy_after,&r->priority_after);
    if(!r->verify_error&&(r->policy_after!=r->policy_before||r->priority_after!=r->priority_before))
        r->verify_error=EINVAL;
    r->stage=4;
    r->return_code=primary?primary:(r->restore_error||r->verify_error?RESTORE_FAILURE:0);
    return r->return_code;
}
#define ARGUMENTS void *mapped,size_t capacity,void *expected,size_t count,uint32_t valid,void *result,size_t result_bytes,double deadline,void *phase,void *receipt,size_t receipt_bytes
#define FORWARD mapped,capacity,expected,count,valid,result,result_bytes,deadline,phase,receipt,receipt_bytes
typedef int (*Ordinary)(ARGUMENTS);
typedef int (*Traced)(ARGUMENTS,void *,size_t);
static int check(void *target,ARGUMENTS,void *trace,size_t trace_bytes,Record *r,size_t bytes) {
    (void)valid; (void)deadline;
    if(!target||!r||bytes!=sizeof(Record)||capacity>SIZE_MAX/4||count>SIZE_MAX/4)return BAD_ARGUMENT;
    if(overlaps(r,bytes,mapped,capacity*4)||overlaps(r,bytes,expected,count*4)||
       overlaps(r,bytes,result,result_bytes)||overlaps(r,bytes,phase,4)||
       overlaps(r,bytes,receipt,receipt_bytes)||overlaps(r,bytes,trace,trace_bytes))return BAD_ARGUMENT;
    memset(r,0,sizeof(*r)); r->abi=0x48534701; return 0;
}
API int hs_ordinary(void *target,ARGUMENTS,Record *r,size_t bytes) {
    int code=check(target,FORWARD,NULL,0,r,bytes);
    if(code)return code;
    code=begin(r); if(code)return code;
    r->delegated=1; code=((Ordinary)target)(FORWARD);
    return finish(r,code);
}
API int hs_traced(void *target,ARGUMENTS,void *trace,size_t trace_bytes,Record *r,size_t bytes) {
    int code=check(target,FORWARD,trace,trace_bytes,r,bytes);
    if(code)return code;
    code=begin(r); if(code)return code;
    r->delegated=1; code=((Traced)target)(FORWARD,trace,trace_bytes);
    return finish(r,code);
}

#ifdef HS_CPU_PROBE
/* Separate no-hardware qualifier binary, never shipped to the hardware runner. */
#include <time.h>
static uint64_t ns(clockid_t clock) {
    struct timespec t;
    if(clock_gettime(clock,&t))return 0;
    return (uint64_t)t.tv_sec*1000000000u+(uint64_t)t.tv_nsec;
}
API int hs_cpu_probe(int elevated,uint64_t work_ns,Record *r,size_t bytes) {
    uint64_t begin_wall,begin_cpu,cpu,wall;
    int code;
    if(!r||bytes!=sizeof(Record)||work_ns>10000000u)return BAD_ARGUMENT;
    memset(r,0,sizeof(*r));r->abi=0x48534701;
    if(elevated) { code=begin(r); if(code)return code; }
    begin_wall=ns(CLOCK_MONOTONIC);begin_cpu=ns(CLOCK_THREAD_CPUTIME_ID);
    do {
        cpu=ns(CLOCK_THREAD_CPUTIME_ID);wall=ns(CLOCK_MONOTONIC);
        if(!cpu||!wall||wall-begin_wall>=40000000u) {
            return elevated?finish(r,1):1;
        }
    } while(cpu-begin_cpu<work_ns);
    return elevated?finish(r,0):0;
}
#endif
