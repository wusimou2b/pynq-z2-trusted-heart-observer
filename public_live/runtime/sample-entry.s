	.arch armv7-a
	.fpu vfpv3-d16
	.eabi_attribute 28, 1
	.eabi_attribute 20, 1
	.eabi_attribute 21, 1
	.eabi_attribute 23, 3
	.eabi_attribute 24, 1
	.eabi_attribute 25, 1
	.eabi_attribute 26, 2
	.eabi_attribute 30, 2
	.eabi_attribute 34, 1
	.eabi_attribute 18, 4
	.file	"sample-entry.c"
	.text
	.align	2
	.global	hm_abi
	.syntax unified
	.arm
	.type	hm_abi, %function
hm_abi:
	@ args = 0, pretend = 0, frame = 0
	@ frame_needed = 0, uses_anonymous_args = 0
	@ link register save eliminated.
	movw	r0, #20995
	movt	r0, 18509
	bx	lr
	.size	hm_abi, .-hm_abi
	.align	2
	.global	hm_arm_mmio_capable
	.syntax unified
	.arm
	.type	hm_arm_mmio_capable, %function
hm_arm_mmio_capable:
	@ args = 0, pretend = 0, frame = 0
	@ frame_needed = 0, uses_anonymous_args = 0
	@ link register save eliminated.
	mov	r0, #1
	bx	lr
	.size	hm_arm_mmio_capable, .-hm_arm_mmio_capable
	.global	__aeabi_ul2d
	.align	2
	.global	hm_now
	.syntax unified
	.arm
	.type	hm_now, %function
hm_now:
	@ args = 0, pretend = 0, frame = 16
	@ frame_needed = 0, uses_anonymous_args = 0
	ldr	r2, .L10+8
	mov	r0, #1
	ldr	r3, .L10+12
.LPIC1:
	add	r2, pc, r2
	str	lr, [sp, #-4]!
	sub	sp, sp, #20
	ldr	r3, [r2, r3]
	add	r1, sp, #4
	ldr	r3, [r3]
	str	r3, [sp, #12]
	mov	r3, #0
	bl	clock_gettime(PLT)
	cmp	r0, #0
	vmovne.f64	d0, #-1.0e+0
	bne	.L4
	ldr	r0, [sp, #8]
	mov	r3, #51712
	movt	r3, 15258
	ldr	r2, [sp, #4]
	asr	r1, r0, #31
	smlal	r0, r1, r2, r3
	bl	__aeabi_ul2d(PLT)
	vldr.64	d7, .L10
	vmov	d6, r0, r1
	vdiv.f64	d0, d6, d7
.L4:
	ldr	r2, .L10+16
	ldr	r3, .L10+12
.LPIC0:
	add	r2, pc, r2
	ldr	r3, [r2, r3]
	ldr	r2, [r3]
	ldr	r3, [sp, #12]
	eors	r2, r3, r2
	mov	r3, #0
	bne	.L9
	add	sp, sp, #20
	@ sp needed
	ldr	pc, [sp], #4
.L9:
	bl	__stack_chk_fail(PLT)
.L11:
	.align	3
.L10:
	.word	0
	.word	1104006501
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC1+8)
	.word	__stack_chk_guard(GOT)
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC0+8)
	.size	hm_now, .-hm_now
	.align	2
	.syntax unified
	.arm
	.type	expired, %function
expired:
	@ args = 0, pretend = 0, frame = 0
	@ frame_needed = 0, uses_anonymous_args = 0
	push	{r4, lr}
	vpush.64	{d8}
	vmov.f64	d8, d0
	bl	hm_now(PLT)
	vabs.f64	d6, d0
	vldr.64	d7, .L17
	vcmp.f64	d6, d7
	vmrs	APSR_nzcv, FPSCR
	bhi	.L15
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L15
	vcmpe.f64	d0, d8
	vldm	sp!, {d8}
	vmrs	APSR_nzcv, FPSCR
	movge	r0, #1
	movlt	r0, #0
	pop	{r4, pc}
.L15:
	vldm	sp!, {d8}
	mov	r0, #3
	pop	{r4, pc}
.L18:
	.align	3
.L17:
	.word	-1
	.word	2146435071
	.size	expired, .-expired
	.global	__aeabi_d2ulz
	.align	2
	.syntax unified
	.arm
	.type	sample_stamp, %function
sample_stamp:
	@ args = 0, pretend = 0, frame = 16
	@ frame_needed = 0, uses_anonymous_args = 0
	ldr	r2, .L26+16
	ldr	r3, .L26+20
.LPIC3:
	add	r2, pc, r2
	push	{r4, r5, r6, r7, r8, r9, lr}
	mov	r4, r0
	vpush.64	{d8, d9}
	sub	sp, sp, #20
	ldr	r3, [r2, r3]
	mov	r6, r1
	ldr	r3, [r3]
	str	r3, [sp, #12]
	mov	r3, #0
	bl	hm_now(PLT)
	vabs.f64	d6, d0
	vldr.64	d7, .L26
	vcmp.f64	d6, d7
	vmrs	APSR_nzcv, FPSCR
	bhi	.L20
	vcmpe.f64	d0, #0
	vmov.f64	d8, d0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L20
	vldr.64	d9, .L26+8
	vcmpe.f64	d0, d9
	vmrs	APSR_nzcv, FPSCR
	bgt	.L20
	add	r1, sp, #4
	mov	r0, #3
	bl	clock_gettime(PLT)
	subs	r5, r0, #0
	bne	.L20
	ldr	r3, [sp, #8]
	vmul.f64	d7, d8, d9
	ldr	r1, [sp, #4]
	mov	r2, #51712
	movt	r2, 15258
	add	r8, r4, r6, lsl #3
	asr	r9, r3, #31
	smlal	r3, r9, r1, r2
	vmov	r0, r1, d7
	mov	r7, r3
	bl	__aeabi_d2ulz(PLT)
	str	r7, [r8, #136]
	mov	r2, #1
	strd	r0, [r8, #32]
	str	r9, [r8, #140]
	ldr	r3, [r4, #4]
	orr	r3, r3, r2, lsl r6
	str	r3, [r4, #4]
	b	.L19
.L20:
	mov	r5, #3
	mov	r3, #1
	str	r3, [r4, #8]
.L19:
	ldr	r2, .L26+24
	ldr	r3, .L26+20
.LPIC2:
	add	r2, pc, r2
	ldr	r3, [r2, r3]
	ldr	r2, [r3]
	ldr	r3, [sp, #12]
	eors	r2, r3, r2
	mov	r3, #0
	bne	.L25
	mov	r0, r5
	add	sp, sp, #20
	@ sp needed
	vldm	sp!, {d8-d9}
	pop	{r4, r5, r6, r7, r8, r9, pc}
.L25:
	bl	__stack_chk_fail(PLT)
.L27:
	.align	3
.L26:
	.word	-1
	.word	2146435071
	.word	0
	.word	1104006501
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC3+8)
	.word	__stack_chk_guard(GOT)
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC2+8)
	.size	sample_stamp, .-sample_stamp
	.align	2
	.syntax unified
	.arm
	.type	write_reg, %function
write_reg:
	@ args = 0, pretend = 0, frame = 0
	@ frame_needed = 0, uses_anonymous_args = 0
	push	{r4, r5, r6, lr}
	mov	r4, r0
	mov	r5, r1
	vpush.64	{d8, d9}
	mov	r6, r2
	vmov.f64	d8, d0
	bl	hm_now(PLT)
	vabs.f64	d7, d0
	vldr.64	d9, .L36
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bhi	.L32
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L32
	vcmpe.f64	d8, d0
	vmrs	APSR_nzcv, FPSCR
	movls	r0, #1
	bls	.L28
	.syntax divided
@ 158 "/home/xilinx/jupyter_notebooks/_codex_compact_sample_entry_build_20261031_01/sample-entry.c" 1
	dmb sy
@ 0 "" 2
	.arm
	.syntax unified
	str	r6, [r4, r5, lsl #2]
	.syntax divided
@ 162 "/home/xilinx/jupyter_notebooks/_codex_compact_sample_entry_build_20261031_01/sample-entry.c" 1
	dsb sy
@ 0 "" 2
	.arm
	.syntax unified
	bl	hm_now(PLT)
	vabs.f64	d7, d0
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bhi	.L32
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L32
	vcmpe.f64	d8, d0
	vldm	sp!, {d8-d9}
	vmrs	APSR_nzcv, FPSCR
	movls	r0, #1
	movhi	r0, #0
	pop	{r4, r5, r6, pc}
.L32:
	mov	r0, #3
.L28:
	vldm	sp!, {d8-d9}
	pop	{r4, r5, r6, pc}
.L37:
	.align	3
.L36:
	.word	-1
	.word	2146435071
	.size	write_reg, .-write_reg
	.align	2
	.syntax unified
	.arm
	.type	read_reg, %function
read_reg:
	@ args = 0, pretend = 0, frame = 0
	@ frame_needed = 0, uses_anonymous_args = 0
	push	{r4, r5, r6, lr}
	mov	r5, r0
	mov	r6, r1
	vpush.64	{d8, d9}
	mov	r4, r2
	vmov.f64	d8, d0
	bl	hm_now(PLT)
	vabs.f64	d7, d0
	vldr.64	d9, .L46
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bhi	.L42
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L42
	vcmpe.f64	d8, d0
	vmrs	APSR_nzcv, FPSCR
	movls	r0, #1
	bls	.L38
	.syntax divided
@ 147 "/home/xilinx/jupyter_notebooks/_codex_compact_sample_entry_build_20261031_01/sample-entry.c" 1
	dmb sy
@ 0 "" 2
	.arm
	.syntax unified
	ldr	r3, [r5, r6, lsl #2]
	str	r3, [r4]
	.syntax divided
@ 151 "/home/xilinx/jupyter_notebooks/_codex_compact_sample_entry_build_20261031_01/sample-entry.c" 1
	dsb sy
@ 0 "" 2
	.arm
	.syntax unified
	bl	hm_now(PLT)
	vabs.f64	d7, d0
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bhi	.L42
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L42
	vcmpe.f64	d8, d0
	vldm	sp!, {d8-d9}
	vmrs	APSR_nzcv, FPSCR
	movls	r0, #1
	movhi	r0, #0
	pop	{r4, r5, r6, pc}
.L42:
	mov	r0, #3
.L38:
	vldm	sp!, {d8-d9}
	pop	{r4, r5, r6, pc}
.L47:
	.align	3
.L46:
	.word	-1
	.word	2146435071
	.size	read_reg, .-read_reg
	.align	2
	.global	hm_read_snapshot
	.syntax unified
	.arm
	.type	hm_read_snapshot, %function
hm_read_snapshot:
	@ args = 4, pretend = 0, frame = 0
	@ frame_needed = 0, uses_anonymous_args = 0
	push	{r4, r5, r6, r7, r8, r9, r10, lr}
	cmp	r2, #0
	cmpne	r0, #0
	vpush.64	{d8, d9}
	ldr	r5, [sp, #48]
	beq	.L70
	subs	r1, r1, #16384
	movne	r1, #1
	cmp	r5, #0
	orreq	r1, r1, #1
	cmp	r3, #174
	orrne	r1, r1, #1
	cmp	r1, #0
	bne	.L70
	orr	r3, r2, r5
	mov	r6, r0
	orr	r3, r3, r0
	ands	r7, r3, #3
	beq	.L75
.L70:
	mov	r0, #2
.L48:
	vldm	sp!, {d8-d9}
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L75:
	vabs.f64	d7, d0
	vldr.64	d6, .L77
	vmov.f64	d8, d0
	vcmp.f64	d7, d6
	vmrs	APSR_nzcv, FPSCR
	bhi	.L70
	cmn	r0, #65536
	cmncc	r2, #696
	bcs	.L70
	add	r3, r2, #696
	cmp	r0, r3
	bcs	.L50
	add	r1, r0, #65536
	cmp	r2, r1
	bcc	.L70
.L50:
	cmn	r5, #4
	beq	.L70
	add	r1, r5, #4
	cmp	r6, r1
	bcs	.L51
	add	r0, r6, #65536
	cmp	r5, r0
	bcc	.L70
.L51:
	cmp	r2, r1
	cmpcc	r5, r3
	bcc	.L70
	mov	r3, #0
	movw	r8, #34953
	movt	r8, 34952
	sub	r4, r2, #4
	vldr.64	d9, .L77
	mov	r9, #30
	str	r3, [r5]
	b	.L61
.L72:
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L54
	vcmpe.f64	d8, d0
	vmrs	APSR_nzcv, FPSCR
	bls	.L60
	cmp	r7, #21
	addls	r3, r7, #40
	bls	.L58
	cmp	r7, #53
	subhi	r3, r7, #54
	addls	r3, r7, #1376
	addls	r3, r3, #10
	umullhi	r1, r2, r8, r3
	lsrhi	r2, r2, #4
	mlshi	r3, r9, r2, r3
	addhi	r3, r3, #1104
	addhi	r3, r3, #2
	addhi	r3, r3, r2, lsl #6
.L58:
	.syntax divided
@ 73 "/home/xilinx/jupyter_notebooks/_codex_compact_sample_entry_build_20261031_01/sample-entry.c" 1
	dmb sy
@ 0 "" 2
	.arm
	.syntax unified
	ldr	r3, [r6, r3, lsl #2]
	str	r3, [r4, #4]!
	.syntax divided
@ 77 "/home/xilinx/jupyter_notebooks/_codex_compact_sample_entry_build_20261031_01/sample-entry.c" 1
	dsb sy
@ 0 "" 2
	.arm
	.syntax unified
	add	r7, r7, #1
	str	r7, [r5]
	bl	hm_now(PLT)
	vabs.f64	d7, d0
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bhi	.L54
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L54
	vcmpe.f64	d8, d0
	vmrs	APSR_nzcv, FPSCR
	bls	.L60
	cmp	r7, #174
	beq	.L76
.L61:
	bl	hm_now(PLT)
	vabs.f64	d7, d0
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bls	.L72
.L54:
	mov	r0, #3
	b	.L48
.L76:
	mov	r0, #0
	b	.L48
.L60:
	mov	r0, #1
	b	.L48
.L78:
	.align	3
.L77:
	.word	-1
	.word	2146435071
	.size	hm_read_snapshot, .-hm_read_snapshot
	.align	2
	.global	hm_result_bytes
	.syntax unified
	.arm
	.type	hm_result_bytes, %function
hm_result_bytes:
	@ args = 0, pretend = 0, frame = 0
	@ frame_needed = 0, uses_anonymous_args = 0
	@ link register save eliminated.
	mov	r0, #480
	bx	lr
	.size	hm_result_bytes, .-hm_result_bytes
	.align	2
	.global	hm_branch_bytes
	.syntax unified
	.arm
	.type	hm_branch_bytes, %function
hm_branch_bytes:
	@ args = 0, pretend = 0, frame = 0
	@ frame_needed = 0, uses_anonymous_args = 0
	@ link register save eliminated.
	mov	r0, #104
	bx	lr
	.size	hm_branch_bytes, .-hm_branch_bytes
	.align	2
	.global	hm_decode_snapshot
	.syntax unified
	.arm
	.type	hm_decode_snapshot, %function
hm_decode_snapshot:
	@ args = 12, pretend = 0, frame = 0
	@ frame_needed = 0, uses_anonymous_args = 0
	push	{r4, r5, r6, r7, r8, r9, r10, lr}
	cmp	r2, #0
	cmpne	r0, #0
	ldr	r4, [sp, #36]
	beq	.L108
	subs	r1, r1, #174
	movne	r1, #1
	cmp	r4, #0
	orreq	r1, r1, #1
	cmp	r1, #0
	bne	.L108
	ldr	r1, [sp, #32]
	cmp	r1, #1
	cmpls	r3, #22
	ldr	r1, [sp, #40]
	movne	r3, #1
	moveq	r3, #0
	cmp	r1, #480
	orrne	r3, r3, #1
	cmp	r3, #0
	bne	.L108
	orr	r3, r0, r2
	and	r1, r4, #7
	and	r3, r3, #3
	mov	r5, r0
	orrs	r3, r3, r1
	moveq	r1, #1
	movne	r1, #0
	cmn	r4, #480
	cmncc	r0, #696
	movcc	r3, #1
	movcs	r3, #0
	tst	r1, r3
	bne	.L123
.L108:
	mov	r0, #2
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L123:
	add	r3, r4, #480
	cmp	r0, r3
	bcs	.L83
	add	r1, r0, #696
	cmp	r4, r1
	bcc	.L108
.L83:
	cmn	r2, #89
	bhi	.L108
	cmp	r2, r3
	bcs	.L84
	add	r3, r2, #88
	cmp	r4, r3
	bcc	.L108
.L84:
	sub	r3, r5, #4
	sub	r2, r2, #4
	add	ip, r5, #84
	b	.L85
.L125:
	cmp	r3, ip
	beq	.L124
.L85:
	ldr	r0, [r3, #4]!
	ldr	r1, [r2, #4]!
	cmp	r0, r1
	beq	.L125
	mov	r0, #4
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L124:
	mov	r1, #0
	mov	r2, #480
	mov	r0, r4
	bl	memset(PLT)
	add	r1, r5, #88
	add	ip, r4, #40
	mov	r0, r4
	vldr.64	d5, .L127
.L86:
	ldr	r2, [r1]
	add	r1, r1, #8
	ldr	r3, [r1, #-4]
	vmov	d7, r2, r3
	vabs.f64	d6, d7
	vcmp.f64	d6, d5
	vmrs	APSR_nzcv, FPSCR
	bhi	.L110
	vstmia.64	r0!, {d7}
	cmp	r0, ip
	bne	.L86
	ldr	r3, [r5, #128]
	ldr	r2, [r5, #132]
	cmp	r3, #16
	ldr	r1, [r5, #136]
	ldr	lr, [r5, #140]
	sbcs	r2, r2, #0
	ldr	r0, [r5, #144]
	ldr	ip, [r5, #148]
	bcs	.L88
	and	r2, r3, #8
	orrs	r6, r2, #0
	bne	.L88
	ldr	r7, [sp, #32]
	and	r6, r3, #1
	cmp	r2, r2
	cmpeq	r6, r7
	bne	.L88
	cmp	lr, r1, asr #31
	bne	.L88
	cmp	ip, r0, asr #31
	bne	.L88
	vmov.f32	s14, r1
	vcvt.f64.s32	d7, d7, #16
	vldr.64	d6, [r4, #16]
	vcmp.f64	d6, d7
	vmrs	APSR_nzcv, FPSCR
	bne	.L88
	ldr	r6, [r5, #204]
	ldr	lr, [r5, #200]
	ldr	ip, [r5, #208]
	ldr	r2, [r5, #212]
	vldr.64	d7, [r4, #32]
	orr	r2, r2, r6
	orr	r6, ip, lr
	cmp	r6, #2
	ldrd	r6, [r5, #192]
	sbcs	r2, r2, #0
	movcs	r2, #1
	movcc	r2, #0
	cmp	r6, #14
	sbcs	r7, r7, #0
	orrcs	r2, r2, #1
	cmp	r2, #0
	bne	.L88
	vcmp.f64	d7, #0
	vldr.64	d6, .L127+8
	vmrs	APSR_nzcv, FPSCR
	vcmp.f64	d7, d6
	movne	r2, #1
	moveq	r2, #0
	vmrs	APSR_nzcv, FPSCR
	moveq	r2, #0
	andne	r2, r2, #1
	cmp	r2, #0
	beq	.L89
	vldr.64	d5, .L127+16
	vldr.64	d6, .L127+24
	vcmp.f64	d7, d5
	vmrs	APSR_nzcv, FPSCR
	vcmp.f64	d7, d6
	movne	r2, #1
	moveq	r2, #0
	vmrs	APSR_nzcv, FPSCR
	moveq	r2, #0
	andne	r2, r2, #1
	cmp	r2, #0
	beq	.L89
	vldr.64	d5, .L127+32
	vmov.f64	d6, #1.0e+0
	vcmp.f64	d7, d5
	vmrs	APSR_nzcv, FPSCR
	vcmp.f64	d7, d6
	movne	r2, #1
	moveq	r2, #0
	vmrs	APSR_nzcv, FPSCR
	moveq	r2, #0
	andne	r2, r2, #1
	cmp	r2, #0
	bne	.L88
.L89:
	str	r3, [r4, #40]
	ldr	r3, [sp, #32]
	str	r1, [r4, #44]
	cmp	r3, #0
	str	r0, [r4, #48]
	str	r6, [r4, #52]
	str	lr, [r4, #56]
	str	ip, [r4, #60]
	beq	.L101
	add	r3, r4, #80
	add	r5, r5, #216
	add	r4, r4, #496
	vldr.64	d6, .L127
.L100:
	ldr	r2, [r5, #40]
	ldr	r6, [r5, #44]
	cmp	r2, #6
	ldr	r9, [r5, #24]
	ldr	r8, [r5, #28]
	sbcs	r1, r6, #0
	ldr	ip, [r5, #96]
	ldr	lr, [r5, #100]
	ldr	r0, [r5, #104]
	ldr	r7, [r5, #108]
	bcs	.L88
	orr	r1, ip, r9
	orr	r1, r1, r0
	cmp	r1, #2
	orr	r1, lr, r8
	orr	r1, r1, r7
	sbcs	r1, r1, #0
	bcs	.L88
	str	r0, [r3, #84]
	str	r2, [r3, #72]
	str	r9, [r3, #76]
	str	ip, [r3, #80]
	ldr	r1, [r5]
	ldr	r0, [r5, #4]
	str	r0, [r3, #52]
	str	r1, [r3, #48]
	ldr	r1, [r5, #8]
	ldr	r0, [r5, #12]
	str	r0, [r3, #60]
	str	r1, [r3, #56]
	ldr	r1, [r5, #32]
	ldr	r0, [r5, #36]
	str	r0, [r3, #68]
	str	r1, [r3, #64]
	ldrd	r0, [r5, #112]
	vmov	d7, r0, r1
	vabs.f64	d5, d7
	vstr.64	d7, [r3, #-16]
	vcmp.f64	d5, d6
	vmrs	APSR_nzcv, FPSCR
	bhi	.L110
	orrs	r6, r2, r6
	beq	.L93
	add	r1, r5, #48
	mov	r0, r3
	add	r2, r1, r2, lsl #3
	b	.L95
.L126:
	cmp	r1, r2
	beq	.L93
.L95:
	ldr	r6, [r1]
	add	r1, r1, #8
	ldr	r7, [r1, #-4]
	vmov	d7, r6, r7
	vabs.f64	d5, d7
	vstmia.64	r0!, {d7}
	vcmp.f64	d5, d6
	vmrs	APSR_nzcv, FPSCR
	bls	.L126
.L110:
	mov	r0, #6
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L88:
	mov	r0, #5
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L93:
	orrs	r8, r9, r8
	beq	.L99
	ldrd	r0, [r5, #16]
	vmov	d7, r0, r1
	vabs.f64	d5, d7
	vstr.64	d7, [r3, #40]
	vcmp.f64	d5, d6
	vmrs	APSR_nzcv, FPSCR
	bhi	.L110
.L99:
	orrs	ip, ip, lr
	beq	.L98
	ldrd	r0, [r5, #88]
	vmov	d7, r0, r1
	vabs.f64	d5, d7
	vstr.64	d7, [r3, #-8]
	vcmp.f64	d5, d6
	vmrs	APSR_nzcv, FPSCR
	bhi	.L110
.L98:
	add	r3, r3, #104
	add	r5, r5, #120
	cmp	r4, r3
	bne	.L100
.L101:
	mov	r0, #0
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L128:
	.align	3
.L127:
	.word	-1
	.word	2146435071
	.word	-1717986918
	.word	1070176665
	.word	-1717986918
	.word	1071225241
	.word	858993459
	.word	1071854387
	.word	-1717986918
	.word	1072273817
	.size	hm_decode_snapshot, .-hm_decode_snapshot
	.align	2
	.syntax unified
	.arm
	.type	hm_transact_sample_trace_body, %function
hm_transact_sample_trace_body:
	@ args = 20, pretend = 0, frame = 728
	@ frame_needed = 0, uses_anonymous_args = 0
	push	{r4, r5, r6, r7, r8, r9, r10, fp, lr}
	cmp	r2, #0
	cmpne	r0, #0
	mov	r6, r0
	ldr	r0, .L169+8
	mov	r4, r2
	ldr	r2, .L169+12
.LPIC5:
	add	r0, pc, r0
	vpush.64	{d8}
	sub	sp, sp, #748
	ldr	r2, [r0, r2]
	ldr	r5, [sp, #796]
	ldr	r2, [r2]
	str	r2, [sp, #740]
	mov	r2, #0
	ldr	r7, [sp, #804]
	mov	r2, #0
	ldr	r8, [sp, #808]
	str	r2, [sp, #28]
	beq	.L153
	cmp	r7, r2
	cmpne	r5, r2
	beq	.L153
	cmp	r3, #22
	cmpeq	r1, #16384
	bne	.L153
	ldr	r3, [sp, #792]
	ldr	r2, [sp, #800]
	cmp	r3, #1
	cmpls	r2, #480
	bne	.L153
	and	r2, r7, #3
	and	r3, r5, #7
	orr	r3, r3, r2
	orr	r2, r6, r4
	and	r2, r2, #3
	orrs	r3, r3, r2
	bne	.L153
	vabs.f64	d7, d0
	vldr.64	d6, .L169
	vmov.f64	d8, d0
	vcmp.f64	d7, d6
	vmrs	APSR_nzcv, FPSCR
	bhi	.L153
	cmn	r4, #89
	cmnls	r6, #65536
	bcc	.L165
.L153:
	mov	r3, #2
.L129:
	ldr	r1, .L169+16
	ldr	r2, .L169+12
.LPIC4:
	add	r1, pc, r1
	ldr	r2, [r1, r2]
	ldr	r1, [r2]
	ldr	r2, [sp, #740]
	eors	r1, r2, r1
	mov	r2, #0
	bne	.L166
	mov	r0, r3
	add	sp, sp, #748
	@ sp needed
	vldm	sp!, {d8}
	pop	{r4, r5, r6, r7, r8, r9, r10, fp, pc}
.L165:
	add	r3, r4, #88
	cmp	r6, r3
	bcs	.L131
	add	r2, r6, #65536
	cmp	r4, r2
	bcc	.L153
.L131:
	cmn	r5, #480
	bcs	.L153
	add	r2, r5, #480
	cmp	r6, r2
	bcs	.L132
	add	r1, r6, #65536
	cmp	r5, r1
	bcc	.L153
.L132:
	cmn	r7, #4
	beq	.L153
	add	r1, r7, #4
	cmp	r6, r1
	bcs	.L133
	add	r0, r6, #65536
	cmp	r7, r0
	bcc	.L153
.L133:
	cmp	r4, r2
	cmpcc	r5, r3
	bcc	.L153
	cmp	r4, r1
	cmpcc	r7, r3
	bcc	.L153
	cmp	r5, r1
	cmpcc	r7, r2
	bcc	.L153
	mov	r3, #0
	mov	r1, #1
	str	r3, [r7]
	mov	r0, r8
	str	r3, [r8, #16]
	bl	sample_stamp(PLT)
	subs	r3, r0, #0
	bne	.L129
	add	r9, sp, #32
	vmov.f64	d0, d8
	mov	r2, r9
	mov	r1, #1
	mov	r0, r6
	bl	read_reg(PLT)
	mov	r1, #2
	str	r0, [sp, #20]
	mov	r0, r8
	bl	sample_stamp(PLT)
	ldr	r3, [sp, #20]
	cmp	r3, #0
	bne	.L129
	cmp	r0, #0
	bne	.L156
	ldr	r2, [sp, #32]
	mov	r3, #1
	movt	r3, 2
	cmp	r2, r3
	movne	r3, #9
	bne	.L129
	mov	r1, #3
	mov	r0, r8
	bl	sample_stamp(PLT)
	subs	r3, r0, #0
	bne	.L129
	vmov.f64	d0, d8
	mov	r2, r9
	mov	r1, #3
	mov	r0, r6
	bl	read_reg(PLT)
	mov	r1, #4
	str	r0, [sp, #20]
	mov	r0, r8
	bl	sample_stamp(PLT)
	ldr	r3, [sp, #20]
	cmp	r3, #0
	bne	.L129
	cmp	r0, #0
	bne	.L156
	ldr	r3, [sp, #32]
	tst	r3, #15
	bne	.L136
	mov	r3, #1
	mov	r1, #5
	str	r3, [r7]
	mov	r0, r8
	str	r3, [r8, #16]
	bl	sample_stamp(PLT)
	subs	r3, r0, #0
	bne	.L129
	sub	fp, r4, #4
	mov	r10, #16
.L135:
	vmov.f64	d0, d8
	ldr	r2, [fp, #4]!
	mov	r1, r10
	mov	r0, r6
	bl	write_reg(PLT)
	subs	r3, r0, #0
	bne	.L129
	add	r10, r10, #1
	cmp	r10, #38
	bne	.L135
	mov	r10, #2
	mov	r1, #6
	str	r10, [r7]
	mov	r0, r8
	str	r10, [r8, #16]
	bl	sample_stamp(PLT)
	subs	r3, r0, #0
	bne	.L129
	vmov.f64	d0, d8
	mov	r2, r10
	mov	r1, r10
	mov	r0, r6
	bl	write_reg(PLT)
	subs	r3, r0, #0
	bne	.L129
	mov	r3, #3
	mov	r1, #7
	str	r3, [r7]
	mov	r0, r8
	str	r3, [r8, #16]
	bl	sample_stamp(PLT)
	subs	r3, r0, #0
	beq	.L137
	b	.L129
.L168:
	tst	r3, #1
	beq	.L167
.L137:
	vmov.f64	d0, d8
	mov	r2, r9
	mov	r1, #3
	mov	r0, r6
	bl	read_reg(PLT)
	subs	r3, r0, #0
	bne	.L129
	ldr	r3, [sp, #32]
	tst	r3, #12
	beq	.L168
.L136:
	mov	r3, #7
	b	.L129
.L166:
	bl	__stack_chk_fail(PLT)
.L156:
	mov	r3, r0
	b	.L129
.L170:
	.align	3
.L169:
	.word	-1
	.word	2146435071
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC5+8)
	.word	__stack_chk_guard(GOT)
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC4+8)
.L167:
	and	r3, r3, #114
	cmp	r3, #114
	movne	r3, #5
	bne	.L129
	vmov.f64	d0, d8
	add	r2, sp, #36
	mov	r1, #6
	mov	r0, r6
	bl	read_reg(PLT)
	subs	r3, r0, #0
	bne	.L129
	vmov.f64	d0, d8
	add	r2, sp, #40
	mov	r1, #7
	mov	r0, r6
	bl	read_reg(PLT)
	subs	r3, r0, #0
	bne	.L129
	ldr	r3, [sp, #36]
	ldr	r2, [r4, #40]
	cmp	r2, r3
	movne	r3, #4
	bne	.L129
	ldr	r3, [sp, #40]
	cmp	r3, #2
	mov	r3, #4
	bne	.L129
	str	r3, [r7]
	mov	r1, #8
	str	r3, [r8, #16]
	mov	r0, r8
	bl	sample_stamp(PLT)
	subs	r3, r0, #0
	bne	.L129
	add	r10, sp, #44
	add	r3, sp, #28
	vmov.f64	d0, d8
	str	r3, [sp]
	mov	r2, r10
	mov	r3, #174
	mov	r1, #16384
	mov	r0, r6
	bl	hm_read_snapshot(PLT)
	subs	r3, r0, #0
	bne	.L129
	ldr	fp, [sp, #28]
	cmp	fp, #174
	movne	r3, #3
	bne	.L129
	vmov.f64	d0, d8
	mov	r2, r9
	mov	r1, #3
	mov	r0, r6
	bl	read_reg(PLT)
	subs	r3, r0, #0
	bne	.L129
	ldr	r3, [sp, #32]
	and	r3, r3, #127
	cmp	r3, #114
	bne	.L136
	mov	r3, #5
	mov	r1, #9
	str	r3, [r7]
	mov	r0, r8
	str	r3, [r8, #16]
	bl	sample_stamp(PLT)
	subs	r3, r0, #0
	bne	.L129
	ldr	r3, [sp, #792]
	mov	r2, r4
	str	r3, [sp]
	mov	r1, fp
	mov	r3, #480
	mov	r0, r10
	str	r3, [sp, #8]
	mov	r3, #22
	str	r5, [sp, #4]
	bl	hm_decode_snapshot(PLT)
	subs	r3, r0, #0
	bne	.L129
	vmov.f64	d0, d8
	bl	expired(PLT)
	subs	r3, r0, #0
	bne	.L129
	vmov.f64	d0, d8
	mov	r2, r9
	mov	r1, #3
	mov	r0, r6
	bl	read_reg(PLT)
	subs	r3, r0, #0
	bne	.L129
	ldr	r3, [sp, #32]
	and	r3, r3, #127
	cmp	r3, #114
	bne	.L136
	mov	r3, #6
	mov	r1, #10
	str	r3, [r7]
	mov	r0, r8
	str	r3, [r8, #16]
	bl	sample_stamp(PLT)
	subs	r3, r0, #0
	bne	.L129
	vmov.f64	d0, d8
	mov	r2, #4
	mov	r1, #2
	mov	r0, r6
	bl	write_reg(PLT)
	subs	r3, r0, #0
	bne	.L129
	mov	r3, #7
	mov	r1, #11
	str	r3, [r7]
	mov	r0, r8
	str	r3, [r8, #16]
	bl	sample_stamp(PLT)
	subs	r3, r0, #0
	bne	.L129
	vmov.f64	d0, d8
	mov	r2, r9
	mov	r1, #3
	mov	r0, r6
	bl	read_reg(PLT)
	subs	r3, r0, #0
	bne	.L129
	ldr	r3, [sp, #32]
	tst	r3, #15
	movne	r3, #8
	bne	.L129
	vmov.f64	d0, d8
	bl	expired(PLT)
	mov	r3, r0
	b	.L129
	.size	hm_transact_sample_trace_body, .-hm_transact_sample_trace_body
	.align	2
	.global	hm_transact_sample
	.syntax unified
	.arm
	.type	hm_transact_sample, %function
hm_transact_sample:
	@ args = 16, pretend = 0, frame = 720
	@ frame_needed = 0, uses_anonymous_args = 0
	push	{r4, r5, r6, r7, r8, r9, r10, lr}
	cmp	r2, #0
	cmpne	r0, #0
	mov	r6, r0
	ldr	r0, .L209+8
	mov	r4, r2
	ldr	r2, .L209+12
.LPIC7:
	add	r0, pc, r0
	vpush.64	{d8}
	sub	sp, sp, #736
	ldr	r2, [r0, r2]
	ldr	r5, [sp, #780]
	ldr	r2, [r2]
	str	r2, [sp, #732]
	mov	r2, #0
	ldr	r7, [sp, #788]
	mov	r2, #0
	str	r2, [sp, #20]
	beq	.L195
	cmp	r7, r2
	cmpne	r5, r2
	beq	.L195
	cmp	r3, #22
	cmpeq	r1, #16384
	bne	.L195
	ldr	r3, [sp, #776]
	ldr	r2, [sp, #784]
	cmp	r3, #1
	cmpls	r2, #480
	bne	.L195
	and	r2, r7, #3
	and	r3, r5, #7
	orr	r3, r3, r2
	orr	r2, r6, r4
	and	r2, r2, #3
	orrs	r3, r3, r2
	bne	.L195
	vabs.f64	d7, d0
	vldr.64	d6, .L209
	vmov.f64	d8, d0
	vcmp.f64	d7, d6
	vmrs	APSR_nzcv, FPSCR
	bhi	.L195
	cmn	r4, #89
	cmnls	r6, #65536
	bcc	.L205
.L195:
	mov	r0, #2
.L171:
	ldr	r2, .L209+16
	ldr	r3, .L209+12
.LPIC6:
	add	r2, pc, r2
	ldr	r3, [r2, r3]
	ldr	r2, [r3]
	ldr	r3, [sp, #732]
	eors	r2, r3, r2
	mov	r3, #0
	bne	.L206
	add	sp, sp, #736
	@ sp needed
	vldm	sp!, {d8}
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L205:
	add	r3, r4, #88
	cmp	r6, r3
	bcs	.L173
	add	r2, r6, #65536
	cmp	r4, r2
	bcc	.L195
.L173:
	cmn	r5, #480
	bcs	.L195
	add	r2, r5, #480
	cmp	r6, r2
	bcs	.L174
	add	r1, r6, #65536
	cmp	r5, r1
	bcc	.L195
.L174:
	cmn	r7, #4
	beq	.L195
	add	r1, r7, #4
	cmp	r6, r1
	bcs	.L175
	add	r0, r6, #65536
	cmp	r7, r0
	bcc	.L195
.L175:
	cmp	r4, r2
	cmpcc	r5, r3
	bcc	.L195
	cmp	r7, r3
	cmpcc	r4, r1
	bcc	.L195
	cmp	r5, r1
	cmpcc	r7, r2
	bcc	.L195
	add	r8, sp, #24
	mov	r3, #0
	vmov.f64	d0, d8
	mov	r2, r8
	mov	r1, #1
	mov	r0, r6
	str	r3, [r7]
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L171
	ldr	r2, [sp, #24]
	mov	r3, #1
	movt	r3, 2
	cmp	r2, r3
	movne	r0, #9
	bne	.L171
	vmov.f64	d0, d8
	mov	r2, r8
	mov	r1, #3
	mov	r0, r6
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L171
	ldr	r3, [sp, #24]
	tst	r3, #15
	bne	.L178
	sub	r10, r4, #4
	mov	r9, #16
	mov	r3, #1
	str	r3, [r7]
.L177:
	vmov.f64	d0, d8
	ldr	r2, [r10, #4]!
	mov	r1, r9
	mov	r0, r6
	bl	write_reg(PLT)
	cmp	r0, #0
	bne	.L171
	add	r9, r9, #1
	cmp	r9, #38
	bne	.L177
	mov	r2, #2
	vmov.f64	d0, d8
	mov	r1, r2
	mov	r0, r6
	str	r2, [r7]
	bl	write_reg(PLT)
	cmp	r0, #0
	bne	.L171
	mov	r3, #3
	str	r3, [r7]
	b	.L179
.L208:
	tst	r3, #1
	beq	.L207
.L179:
	vmov.f64	d0, d8
	mov	r2, r8
	mov	r1, #3
	mov	r0, r6
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L171
	ldr	r3, [sp, #24]
	tst	r3, #12
	beq	.L208
.L178:
	mov	r0, #7
	b	.L171
.L206:
	bl	__stack_chk_fail(PLT)
.L207:
	and	r3, r3, #114
	cmp	r3, #114
	movne	r0, #5
	bne	.L171
	vmov.f64	d0, d8
	add	r2, sp, #28
	mov	r1, #6
	mov	r0, r6
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L171
	vmov.f64	d0, d8
	add	r2, sp, #32
	mov	r1, #7
	mov	r0, r6
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L171
	ldr	r2, [r4, #40]
	ldr	r3, [sp, #28]
	cmp	r2, r3
	bne	.L199
	ldr	r3, [sp, #32]
	cmp	r3, #2
	bne	.L199
	add	r9, sp, #36
	mov	r3, #4
	vmov.f64	d0, d8
	str	r3, [r7]
	mov	r2, r9
	add	r3, sp, #20
	mov	r1, #16384
	str	r3, [sp]
	mov	r0, r6
	mov	r3, #174
	bl	hm_read_snapshot(PLT)
	cmp	r0, #0
	bne	.L171
	ldr	r3, [sp, #20]
	cmp	r3, #174
	movne	r0, #3
	bne	.L171
	vmov.f64	d0, d8
	mov	r2, r8
	mov	r1, #3
	mov	r0, r6
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L171
	ldr	r3, [sp, #24]
	and	r3, r3, #127
	cmp	r3, #114
	bne	.L178
	ldr	r3, [sp, #776]
	mov	r2, r4
	str	r3, [sp]
	mov	r0, r9
	mov	r3, #5
	str	r5, [sp, #4]
	mov	r1, #174
	str	r3, [r7]
	mov	r3, #480
	str	r3, [sp, #8]
	mov	r3, #22
	bl	hm_decode_snapshot(PLT)
	cmp	r0, #0
	bne	.L171
	vmov.f64	d0, d8
	bl	expired(PLT)
	cmp	r0, #0
	bne	.L171
	vmov.f64	d0, d8
	mov	r2, r8
	mov	r1, #3
	mov	r0, r6
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L171
	ldr	r3, [sp, #24]
	and	r3, r3, #127
	cmp	r3, #114
	bne	.L178
	mov	r3, #6
	vmov.f64	d0, d8
	mov	r2, #4
	mov	r1, #2
	mov	r0, r6
	str	r3, [r7]
	bl	write_reg(PLT)
	cmp	r0, #0
	bne	.L171
	mov	r3, #7
	vmov.f64	d0, d8
	mov	r2, r8
	mov	r1, #3
	mov	r0, r6
	str	r3, [r7]
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L171
	ldr	r3, [sp, #24]
	tst	r3, #15
	movne	r0, #8
	bne	.L171
	vmov.f64	d0, d8
	bl	expired(PLT)
	b	.L171
.L199:
	mov	r0, #4
	b	.L171
.L210:
	.align	3
.L209:
	.word	-1
	.word	2146435071
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC7+8)
	.word	__stack_chk_guard(GOT)
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC6+8)
	.size	hm_transact_sample, .-hm_transact_sample
	.align	2
	.global	hm_fault_receipt_bytes
	.syntax unified
	.arm
	.type	hm_fault_receipt_bytes, %function
hm_fault_receipt_bytes:
	@ args = 0, pretend = 0, frame = 0
	@ frame_needed = 0, uses_anonymous_args = 0
	@ link register save eliminated.
	mov	r0, #48
	bx	lr
	.size	hm_fault_receipt_bytes, .-hm_fault_receipt_bytes
	.align	2
	.global	hm_transact_sample_fault_receipt
	.syntax unified
	.arm
	.type	hm_transact_sample_fault_receipt, %function
hm_transact_sample_fault_receipt:
	@ args = 24, pretend = 0, frame = 64
	@ frame_needed = 0, uses_anonymous_args = 0
	push	{r4, r5, r6, r7, r8, r9, r10, fp, lr}
	mov	r6, r2
	ldr	r2, .L238
	mov	r8, r3
	ldr	r3, .L238+4
.LPIC10:
	add	r2, pc, r2
	vpush.64	{d8}
	sub	sp, sp, #84
	ldr	lr, .L238+8
	mov	r5, r0
	mov	r7, r1
	ldr	r3, [r2, r3]
.LPIC8:
	add	lr, pc, lr
	ldr	r4, [sp, #144]
	mov	r2, #0
	ldr	r3, [r3]
	str	r3, [sp, #76]
	mov	r3, #0
	ldr	r3, [sp, #148]
	str	r2, [sp, #28]
	add	r9, sp, #52
	subs	r3, r3, #48
	str	r2, [sp, #32]
	movne	r3, #1
	str	r2, [sp, #36]
	cmp	r4, #0
	orreq	r3, r3, #1
	str	r2, [sp, #40]
	cmp	r3, #0
	str	r2, [sp, #44]
	str	r2, [sp, #48]
	mov	ip, r9
	ldmia	lr!, {r0, r1, r2, r3}
	stmia	ip!, {r0, r1, r2, r3}
	ldr	r10, [sp, #132]
	ldr	fp, [sp, #140]
	ldm	lr, {r0, r1}
	stm	ip, {r0, r1}
	bne	.L231
	ands	r3, r4, #3
	str	r3, [sp, #20]
	bne	.L231
	cmn	r4, #49
	cmnls	r5, #65536
	bcc	.L234
.L231:
	mov	r6, #2
.L212:
	ldr	r2, .L238+12
	ldr	r3, .L238+4
.LPIC9:
	add	r2, pc, r2
	ldr	r3, [r2, r3]
	ldr	r2, [r3]
	ldr	r3, [sp, #76]
	eors	r2, r3, r2
	mov	r3, #0
	bne	.L235
	mov	r0, r6
	add	sp, sp, #84
	@ sp needed
	vldm	sp!, {d8}
	pop	{r4, r5, r6, r7, r8, r9, r10, fp, pc}
.L234:
	add	r3, r5, #65536
	vmov.f64	d8, d0
	cmp	r4, r3
	bcs	.L214
	add	r3, r4, #48
	cmp	r5, r3
	bcc	.L231
.L214:
	cmn	r6, #89
	bhi	.L231
	add	r3, r6, #88
	cmp	r4, r3
	bcc	.L236
.L215:
	cmn	r10, #480
	bcs	.L231
	add	r3, r10, #480
	cmp	r4, r3
	bcs	.L216
	add	r3, r4, #48
	cmp	r10, r3
	bcc	.L231
.L216:
	cmn	fp, #5
	bhi	.L231
	add	r3, fp, #4
	cmp	r4, r3
	bcs	.L217
	add	r3, r4, #48
	cmp	fp, r3
	bcc	.L231
.L217:
	mov	r2, #48
	mov	r1, #0
	mov	r0, r4
	bl	memset(PLT)
	ldr	r0, [sp, #136]
	str	r0, [sp, #8]
	mov	r3, r8
	ldr	r0, [sp, #128]
	mov	r2, r6
	str	r0, [sp]
	vmov.f64	d0, d8
	str	r10, [sp, #4]
	mov	r1, r7
	str	fp, [sp, #12]
	mov	r0, r5
	movw	ip, #17921
	movt	ip, 18509
	str	ip, [r4]
	bl	hm_transact_sample(PLT)
	sub	r3, r0, #7
	mov	r6, r0
	cmp	r3, #1
	str	r0, [r4, #4]
	bhi	.L212
	add	r10, sp, #24
	ldr	r3, [fp]
	mov	r8, r10
	mov	r7, #1
	str	r3, [r4, #8]
	str	r7, [r4, #12]
.L220:
	ldr	r3, [sp, #20]
	vmov.f64	d0, d8
	mov	r2, r10
	mov	r0, r5
	ldr	r1, [r9, r3, lsl #2]
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L237
	ldr	r2, [sp, #20]
	ldr	r3, [r4, #16]
	orr	r3, r3, r7, lsl r2
	str	r3, [r4, #16]
	add	r3, r2, #1
	str	r3, [sp, #20]
	cmp	r3, #6
	ldr	r3, [sp, #24]
	str	r3, [r8, #4]!
	bne	.L220
.L219:
	ldrd	r2, [sp, #28]
	strd	r2, [r4, #24]
	ldr	r3, [sp, #40]
	ldr	r1, [sp, #36]
	ldr	r2, [sp, #44]
	str	r3, [r4, #36]
	ldr	r3, [sp, #48]
	str	r1, [r4, #32]
	strd	r2, [r4, #40]
	b	.L212
.L236:
	add	r3, r4, #48
	cmp	r6, r3
	bcc	.L231
	b	.L215
.L237:
	str	r0, [r4, #20]
	b	.L219
.L235:
	bl	__stack_chk_fail(PLT)
.L239:
	.align	2
.L238:
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC10+8)
	.word	__stack_chk_guard(GOT)
	.word	.LANCHOR0-(.LPIC8+8)
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC9+8)
	.size	hm_transact_sample_fault_receipt, .-hm_transact_sample_fault_receipt
	.align	2
	.global	hm_sample_trace_bytes
	.syntax unified
	.arm
	.type	hm_sample_trace_bytes, %function
hm_sample_trace_bytes:
	@ args = 0, pretend = 0, frame = 0
	@ frame_needed = 0, uses_anonymous_args = 0
	@ link register save eliminated.
	mov	r0, #240
	bx	lr
	.size	hm_sample_trace_bytes, .-hm_sample_trace_bytes
	.align	2
	.global	hm_transact_sample_entry_trace
	.syntax unified
	.arm
	.type	hm_transact_sample_entry_trace, %function
hm_transact_sample_entry_trace:
	@ args = 32, pretend = 0, frame = 112
	@ frame_needed = 0, uses_anonymous_args = 0
	push	{r4, r5, r6, r7, r8, r9, r10, fp, lr}
	mov	r8, r2
	ldr	r2, .L284+16
	vpush.64	{d8, d9}
	sub	sp, sp, #140
.LPIC13:
	add	r2, pc, r2
	add	r9, sp, #76
	mov	r7, r0
	vmov.f64	d9, d0
	str	r3, [sp, #36]
	ldr	r3, .L284+20
	str	r1, [sp, #32]
	ldr	r4, [sp, #216]
	ldr	r10, [sp, #196]
	ldr	r3, [r2, r3]
	ldr	fp, [sp, #208]
	ldr	r3, [r3]
	str	r3, [sp, #132]
	mov	r3, #0
	ldr	r3, [sp, #204]
	str	r3, [sp, #28]
	bl	hm_now(PLT)
	mov	r1, r9
	mov	r0, #3
	vmov.f64	d8, d0
	bl	clock_gettime(PLT)
	subs	r6, r0, #0
	moveq	r2, #51712
	movne	r5, #0
	movteq	r2, 15258
	movne	r6, #3
	ldreq	r5, [sp, #80]
	movne	r3, r5
	ldreq	r1, [sp, #76]
	asreq	r3, r5, #31
	smlaleq	r5, r3, r1, r2
	cmp	r4, #0
	beq	.L271
	ands	r2, r4, #7
	ldr	r1, [sp, #220]
	movne	r2, #1
	cmp	r1, #240
	orrne	r2, r2, #1
	cmp	r2, #0
	bne	.L271
	cmn	r4, #241
	cmnls	r7, #65536
	bcc	.L281
.L271:
	mov	r6, #2
.L241:
	ldr	r2, .L284+24
	ldr	r3, .L284+20
.LPIC12:
	add	r2, pc, r2
	ldr	r3, [r2, r3]
	ldr	r2, [r3]
	ldr	r3, [sp, #132]
	eors	r2, r3, r2
	mov	r3, #0
	bne	.L282
	mov	r0, r6
	add	sp, sp, #140
	@ sp needed
	vldm	sp!, {d8-d9}
	pop	{r4, r5, r6, r7, r8, r9, r10, fp, pc}
.L281:
	add	r2, r7, #65536
	str	r2, [sp, #40]
	cmp	r4, r2
	bcs	.L244
	add	r2, r4, #240
	cmp	r7, r2
	bcc	.L271
.L244:
	cmn	r8, #89
	bhi	.L271
	add	r2, r8, #88
	str	r2, [sp, #44]
	cmp	r4, r2
	bcs	.L245
	add	r2, r4, #240
	cmp	r8, r2
	bcc	.L271
.L245:
	cmn	r10, #480
	bcs	.L271
	add	r2, r10, #480
	str	r2, [sp, #48]
	cmp	r4, r2
	bcs	.L246
	add	r2, r4, #240
	cmp	r10, r2
	bcc	.L271
.L246:
	ldr	r1, [sp, #28]
	cmn	r1, #5
	bhi	.L271
	add	r2, r1, #4
	str	r2, [sp, #52]
	cmp	r4, r2
	bcs	.L247
	add	r2, r4, #240
	cmp	r1, r2
	bcc	.L271
.L247:
	cmn	fp, #49
	bhi	.L271
	add	r2, fp, #48
	str	r2, [sp, #56]
	cmp	r4, r2
	bcs	.L248
	add	r2, r4, #240
	cmp	fp, r2
	bcc	.L271
.L248:
	mov	r2, #240
	mov	r1, #0
	mov	r0, r4
	str	r3, [sp, #60]
	bl	memset(PLT)
	movw	r2, #21505
	movt	r2, 18509
	cmp	r6, #0
	str	r2, [r4]
	bne	.L249
	vabs.f64	d7, d8
	vldr.64	d6, .L284
	vcmp.f64	d7, d6
	vmrs	APSR_nzcv, FPSCR
	bhi	.L249
	vcmpe.f64	d8, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L249
	vldr.64	d7, .L284+8
	ldr	r3, [sp, #60]
	vcmpe.f64	d8, d7
	vmrs	APSR_nzcv, FPSCR
	bgt	.L249
	vmul.f64	d7, d8, d7
	str	r3, [sp, #68]
	add	r3, sp, #108
	str	r3, [sp, #64]
	add	r3, sp, #84
	str	r3, [sp, #60]
	vmov	r0, r1, d7
	bl	__aeabi_d2ulz(PLT)
	ldr	r3, [sp, #68]
	str	r3, [r4, #140]
	ldr	r3, [sp, #60]
	ldr	lr, .L284+28
	strd	r0, [r4, #32]
	str	r6, [r3, #4]
.LPIC11:
	add	lr, pc, lr
	str	r6, [r3, #8]
	str	r6, [r3, #12]
	str	r6, [r3, #16]
	str	r6, [r3, #20]
	ldr	r3, [sp, #212]
	ldr	ip, [sp, #64]
	subs	r3, r3, #48
	str	r5, [r4, #136]
	movne	r3, #1
	str	r6, [sp, #84]
	cmp	fp, #0
	orreq	r3, r3, #1
	cmp	r3, #0
	mov	r3, #1
	str	r3, [r4, #4]
	ldmia	lr!, {r0, r1, r2, r3}
	stmia	ip!, {r0, r1, r2, r3}
	ldm	lr, {r0, r1}
	stm	ip, {r0, r1}
	bne	.L277
	ands	r5, fp, #3
	bne	.L277
	ldr	r3, [sp, #56]
	ldr	r2, [sp, #40]
	cmp	fp, r2
	cmpcc	r7, r3
	bcc	.L277
	ldr	r2, [sp, #44]
	cmp	fp, r2
	cmpcc	r8, r3
	bcc	.L277
	ldr	r2, [sp, #48]
	cmp	fp, r2
	cmpcc	r10, r3
	bcc	.L277
	ldr	r6, [sp, #28]
	ldr	r1, [sp, #52]
	cmp	fp, r1
	cmpcc	r6, r3
	bcc	.L277
	mov	r2, #48
	mov	r1, #0
	mov	r0, fp
	bl	memset(PLT)
	ldr	r0, [sp, #200]
	str	r0, [sp, #8]
	mov	r2, r8
	ldr	r0, [sp, #192]
	vmov.f64	d0, d9
	str	r6, [sp, #12]
	movw	ip, #17921
	movt	ip, 18509
	str	r0, [sp]
	ldr	r3, [sp, #36]
	mov	r0, r7
	str	r10, [sp, #4]
	mov	r8, r6
	str	r4, [sp, #16]
	ldr	r1, [sp, #32]
	str	ip, [fp]
	bl	hm_transact_sample_trace_body(PLT)
	sub	r3, r0, #7
	mov	r6, r0
	cmp	r3, #1
	str	r0, [fp, #4]
	bhi	.L253
	ldr	r10, [sp, #64]
	ldr	r3, [r8]
	mov	r8, #1
	str	r3, [fp, #8]
	str	r8, [fp, #12]
.L256:
	vmov.f64	d0, d9
	ldr	r1, [r10], #4
	mov	r2, r9
	mov	r0, r7
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L283
	ldr	r3, [fp, #16]
	ldr	r2, [sp, #60]
	orr	r3, r3, r8, lsl r5
	str	r3, [fp, #16]
	ldr	r3, [sp, #76]
	str	r3, [r2, r5, lsl #2]
	add	r5, r5, #1
	cmp	r5, #6
	bne	.L256
.L255:
	ldrd	r2, [sp, #84]
	strd	r2, [fp, #24]
	ldrd	r2, [sp, #92]
	strd	r2, [fp, #32]
	ldrd	r2, [sp, #100]
	strd	r2, [fp, #40]
	b	.L252
.L249:
	mov	r3, #3
	mov	r2, #1
	mov	r6, r3
	strd	r2, [r4, #8]
	b	.L241
.L282:
	bl	__stack_chk_fail(PLT)
.L253:
	mov	r1, #12
	mov	r0, r4
	bl	sample_stamp(PLT)
	cmp	r6, #0
	moveq	r6, r0
.L257:
	str	r6, [r4, #12]
	b	.L241
.L277:
	mov	r6, #2
.L252:
	mov	r1, #12
	mov	r0, r4
	bl	sample_stamp(PLT)
	b	.L257
.L283:
	str	r0, [fp, #20]
	b	.L255
.L285:
	.align	3
.L284:
	.word	-1
	.word	2146435071
	.word	0
	.word	1104006501
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC13+8)
	.word	__stack_chk_guard(GOT)
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC12+8)
	.word	.LANCHOR0-(.LPIC11+8)
	.size	hm_transact_sample_entry_trace, .-hm_transact_sample_entry_trace
	.section	.rodata
	.align	2
	.set	.LANCHOR0,. + 0
.LC0:
	.word	3
	.word	10
	.word	8
	.word	9
	.word	11
	.word	14
	.ident	"GCC: (Ubuntu 11.2.0-19ubuntu1) 11.2.0"
	.section	.note.GNU-stack,"",%progbits
