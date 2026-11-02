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
	.file	"main_heart_readback.c"
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
	vldr.64	d9, .L20
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bhi	.L16
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L16
	vcmpe.f64	d8, d0
	vmrs	APSR_nzcv, FPSCR
	movls	r0, #1
	bls	.L12
	.syntax divided
@ 158 "/home/xilinx/jupyter_notebooks/v3b25 main native transaction budget 20261026/main_heart_readback.c" 1
	dmb sy
@ 0 "" 2
	.arm
	.syntax unified
	str	r6, [r4, r5, lsl #2]
	.syntax divided
@ 162 "/home/xilinx/jupyter_notebooks/v3b25 main native transaction budget 20261026/main_heart_readback.c" 1
	dsb sy
@ 0 "" 2
	.arm
	.syntax unified
	bl	hm_now(PLT)
	vabs.f64	d7, d0
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bhi	.L16
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L16
	vcmpe.f64	d8, d0
	vldm	sp!, {d8-d9}
	vmrs	APSR_nzcv, FPSCR
	movls	r0, #1
	movhi	r0, #0
	pop	{r4, r5, r6, pc}
.L16:
	mov	r0, #3
.L12:
	vldm	sp!, {d8-d9}
	pop	{r4, r5, r6, pc}
.L21:
	.align	3
.L20:
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
	vldr.64	d9, .L30
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bhi	.L26
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L26
	vcmpe.f64	d8, d0
	vmrs	APSR_nzcv, FPSCR
	movls	r0, #1
	bls	.L22
	.syntax divided
@ 147 "/home/xilinx/jupyter_notebooks/v3b25 main native transaction budget 20261026/main_heart_readback.c" 1
	dmb sy
@ 0 "" 2
	.arm
	.syntax unified
	ldr	r3, [r5, r6, lsl #2]
	str	r3, [r4]
	.syntax divided
@ 151 "/home/xilinx/jupyter_notebooks/v3b25 main native transaction budget 20261026/main_heart_readback.c" 1
	dsb sy
@ 0 "" 2
	.arm
	.syntax unified
	bl	hm_now(PLT)
	vabs.f64	d7, d0
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bhi	.L26
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L26
	vcmpe.f64	d8, d0
	vldm	sp!, {d8-d9}
	vmrs	APSR_nzcv, FPSCR
	movls	r0, #1
	movhi	r0, #0
	pop	{r4, r5, r6, pc}
.L26:
	mov	r0, #3
.L22:
	vldm	sp!, {d8-d9}
	pop	{r4, r5, r6, pc}
.L31:
	.align	3
.L30:
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
	beq	.L54
	subs	r1, r1, #16384
	movne	r1, #1
	cmp	r5, #0
	orreq	r1, r1, #1
	cmp	r3, #174
	orrne	r1, r1, #1
	cmp	r1, #0
	bne	.L54
	orr	r3, r2, r5
	mov	r6, r0
	orr	r3, r3, r0
	ands	r7, r3, #3
	beq	.L59
.L54:
	mov	r0, #2
.L32:
	vldm	sp!, {d8-d9}
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L59:
	vabs.f64	d7, d0
	vldr.64	d6, .L61
	vmov.f64	d8, d0
	vcmp.f64	d7, d6
	vmrs	APSR_nzcv, FPSCR
	bhi	.L54
	cmn	r0, #65536
	cmncc	r2, #696
	bcs	.L54
	add	r3, r2, #696
	cmp	r0, r3
	bcs	.L34
	add	r1, r0, #65536
	cmp	r2, r1
	bcc	.L54
.L34:
	cmn	r5, #4
	beq	.L54
	add	r1, r5, #4
	cmp	r6, r1
	bcs	.L35
	add	r0, r6, #65536
	cmp	r5, r0
	bcc	.L54
.L35:
	cmp	r2, r1
	cmpcc	r5, r3
	bcc	.L54
	mov	r3, #0
	movw	r8, #34953
	movt	r8, 34952
	sub	r4, r2, #4
	vldr.64	d9, .L61
	mov	r9, #30
	str	r3, [r5]
	b	.L45
.L56:
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L38
	vcmpe.f64	d8, d0
	vmrs	APSR_nzcv, FPSCR
	bls	.L44
	cmp	r7, #21
	addls	r3, r7, #40
	bls	.L42
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
.L42:
	.syntax divided
@ 73 "/home/xilinx/jupyter_notebooks/v3b25 main native transaction budget 20261026/main_heart_readback.c" 1
	dmb sy
@ 0 "" 2
	.arm
	.syntax unified
	ldr	r3, [r6, r3, lsl #2]
	str	r3, [r4, #4]!
	.syntax divided
@ 77 "/home/xilinx/jupyter_notebooks/v3b25 main native transaction budget 20261026/main_heart_readback.c" 1
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
	bhi	.L38
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L38
	vcmpe.f64	d8, d0
	vmrs	APSR_nzcv, FPSCR
	bls	.L44
	cmp	r7, #174
	beq	.L60
.L45:
	bl	hm_now(PLT)
	vabs.f64	d7, d0
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bls	.L56
.L38:
	mov	r0, #3
	b	.L32
.L60:
	mov	r0, #0
	b	.L32
.L44:
	mov	r0, #1
	b	.L32
.L62:
	.align	3
.L61:
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
	beq	.L92
	subs	r1, r1, #174
	movne	r1, #1
	cmp	r4, #0
	orreq	r1, r1, #1
	cmp	r1, #0
	bne	.L92
	ldr	r1, [sp, #32]
	cmp	r1, #1
	cmpls	r3, #22
	ldr	r1, [sp, #40]
	movne	r3, #1
	moveq	r3, #0
	cmp	r1, #480
	orrne	r3, r3, #1
	cmp	r3, #0
	bne	.L92
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
	bne	.L107
.L92:
	mov	r0, #2
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L107:
	add	r3, r4, #480
	cmp	r0, r3
	bcs	.L67
	add	r1, r0, #696
	cmp	r4, r1
	bcc	.L92
.L67:
	cmn	r2, #89
	bhi	.L92
	cmp	r2, r3
	bcs	.L68
	add	r3, r2, #88
	cmp	r4, r3
	bcc	.L92
.L68:
	sub	r3, r5, #4
	sub	r2, r2, #4
	add	ip, r5, #84
	b	.L69
.L109:
	cmp	r3, ip
	beq	.L108
.L69:
	ldr	r0, [r3, #4]!
	ldr	r1, [r2, #4]!
	cmp	r0, r1
	beq	.L109
	mov	r0, #4
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L108:
	mov	r1, #0
	mov	r2, #480
	mov	r0, r4
	bl	memset(PLT)
	add	r1, r5, #88
	add	ip, r4, #40
	mov	r0, r4
	vldr.64	d5, .L111
.L70:
	ldr	r2, [r1]
	add	r1, r1, #8
	ldr	r3, [r1, #-4]
	vmov	d7, r2, r3
	vabs.f64	d6, d7
	vcmp.f64	d6, d5
	vmrs	APSR_nzcv, FPSCR
	bhi	.L94
	vstmia.64	r0!, {d7}
	cmp	r0, ip
	bne	.L70
	ldr	r3, [r5, #128]
	ldr	r2, [r5, #132]
	cmp	r3, #16
	ldr	r1, [r5, #136]
	ldr	lr, [r5, #140]
	sbcs	r2, r2, #0
	ldr	r0, [r5, #144]
	ldr	ip, [r5, #148]
	bcs	.L72
	and	r2, r3, #8
	orrs	r6, r2, #0
	bne	.L72
	ldr	r7, [sp, #32]
	and	r6, r3, #1
	cmp	r2, r2
	cmpeq	r6, r7
	bne	.L72
	cmp	lr, r1, asr #31
	bne	.L72
	cmp	ip, r0, asr #31
	bne	.L72
	vmov.f32	s14, r1
	vcvt.f64.s32	d7, d7, #16
	vldr.64	d6, [r4, #16]
	vcmp.f64	d6, d7
	vmrs	APSR_nzcv, FPSCR
	bne	.L72
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
	bne	.L72
	vcmp.f64	d7, #0
	vldr.64	d6, .L111+8
	vmrs	APSR_nzcv, FPSCR
	vcmp.f64	d7, d6
	movne	r2, #1
	moveq	r2, #0
	vmrs	APSR_nzcv, FPSCR
	moveq	r2, #0
	andne	r2, r2, #1
	cmp	r2, #0
	beq	.L73
	vldr.64	d5, .L111+16
	vldr.64	d6, .L111+24
	vcmp.f64	d7, d5
	vmrs	APSR_nzcv, FPSCR
	vcmp.f64	d7, d6
	movne	r2, #1
	moveq	r2, #0
	vmrs	APSR_nzcv, FPSCR
	moveq	r2, #0
	andne	r2, r2, #1
	cmp	r2, #0
	beq	.L73
	vldr.64	d5, .L111+32
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
	bne	.L72
.L73:
	str	r3, [r4, #40]
	ldr	r3, [sp, #32]
	str	r1, [r4, #44]
	cmp	r3, #0
	str	r0, [r4, #48]
	str	r6, [r4, #52]
	str	lr, [r4, #56]
	str	ip, [r4, #60]
	beq	.L85
	add	r3, r4, #80
	add	r5, r5, #216
	add	r4, r4, #496
	vldr.64	d6, .L111
.L84:
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
	bcs	.L72
	orr	r1, ip, r9
	orr	r1, r1, r0
	cmp	r1, #2
	orr	r1, lr, r8
	orr	r1, r1, r7
	sbcs	r1, r1, #0
	bcs	.L72
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
	bhi	.L94
	orrs	r6, r2, r6
	beq	.L77
	add	r1, r5, #48
	mov	r0, r3
	add	r2, r1, r2, lsl #3
	b	.L79
.L110:
	cmp	r1, r2
	beq	.L77
.L79:
	ldr	r6, [r1]
	add	r1, r1, #8
	ldr	r7, [r1, #-4]
	vmov	d7, r6, r7
	vabs.f64	d5, d7
	vstmia.64	r0!, {d7}
	vcmp.f64	d5, d6
	vmrs	APSR_nzcv, FPSCR
	bls	.L110
.L94:
	mov	r0, #6
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L72:
	mov	r0, #5
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L77:
	orrs	r8, r9, r8
	beq	.L83
	ldrd	r0, [r5, #16]
	vmov	d7, r0, r1
	vabs.f64	d5, d7
	vstr.64	d7, [r3, #40]
	vcmp.f64	d5, d6
	vmrs	APSR_nzcv, FPSCR
	bhi	.L94
.L83:
	orrs	ip, ip, lr
	beq	.L82
	ldrd	r0, [r5, #88]
	vmov	d7, r0, r1
	vabs.f64	d5, d7
	vstr.64	d7, [r3, #-8]
	vcmp.f64	d5, d6
	vmrs	APSR_nzcv, FPSCR
	bhi	.L94
.L82:
	add	r3, r3, #104
	add	r5, r5, #120
	cmp	r4, r3
	bne	.L84
.L85:
	mov	r0, #0
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.L112:
	.align	3
.L111:
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
	.global	hm_transact_sample
	.syntax unified
	.arm
	.type	hm_transact_sample, %function
hm_transact_sample:
	@ args = 16, pretend = 0, frame = 720
	@ frame_needed = 0, uses_anonymous_args = 0
	push	{r4, r5, r6, r7, r8, r9, lr}
	cmp	r2, #0
	cmpne	r0, #0
	mov	r6, r0
	ldr	r0, .L151+8
	mov	r4, r2
	ldr	r2, .L151+12
.LPIC3:
	add	r0, pc, r0
	vpush.64	{d8, d9}
	sub	sp, sp, #740
	ldr	r2, [r0, r2]
	ldr	r5, [sp, #788]
	ldr	r2, [r2]
	str	r2, [sp, #732]
	mov	r2, #0
	ldr	r7, [sp, #796]
	mov	r2, #0
	str	r2, [sp, #20]
	beq	.L137
	cmp	r7, r2
	cmpne	r5, r2
	beq	.L137
	cmp	r3, #22
	cmpeq	r1, #16384
	bne	.L137
	ldr	r3, [sp, #784]
	ldr	r2, [sp, #792]
	cmp	r3, #1
	cmpls	r2, #480
	bne	.L137
	and	r2, r7, #3
	and	r3, r5, #7
	orr	r3, r3, r2
	orr	r2, r6, r4
	and	r2, r2, #3
	orrs	r3, r3, r2
	bne	.L137
	vabs.f64	d7, d0
	vldr.64	d6, .L151
	vmov.f64	d8, d0
	vcmp.f64	d7, d6
	vmrs	APSR_nzcv, FPSCR
	bhi	.L137
	cmn	r4, #89
	cmnls	r6, #65536
	bcc	.L147
.L137:
	mov	r0, #2
.L113:
	ldr	r2, .L151+16
	ldr	r3, .L151+12
.LPIC2:
	add	r2, pc, r2
	ldr	r3, [r2, r3]
	ldr	r2, [r3]
	ldr	r3, [sp, #732]
	eors	r2, r3, r2
	mov	r3, #0
	bne	.L148
	add	sp, sp, #740
	@ sp needed
	vldm	sp!, {d8-d9}
	pop	{r4, r5, r6, r7, r8, r9, pc}
.L147:
	add	r3, r4, #88
	cmp	r6, r3
	bcs	.L115
	add	r2, r6, #65536
	cmp	r4, r2
	bcc	.L137
.L115:
	cmn	r5, #480
	bcs	.L137
	add	r2, r5, #480
	cmp	r6, r2
	bcs	.L116
	add	r1, r6, #65536
	cmp	r5, r1
	bcc	.L137
.L116:
	cmn	r7, #4
	beq	.L137
	add	r1, r7, #4
	cmp	r6, r1
	bcs	.L117
	add	r0, r6, #65536
	cmp	r7, r0
	bcc	.L137
.L117:
	cmp	r4, r2
	cmpcc	r5, r3
	bcc	.L137
	cmp	r4, r1
	cmpcc	r7, r3
	bcc	.L137
	cmp	r5, r1
	cmpcc	r7, r2
	bcc	.L137
	sub	r9, r4, #4
	mov	r8, #16
	mov	r3, #1
	str	r3, [r7]
.L118:
	vmov.f64	d0, d8
	ldr	r2, [r9, #4]!
	mov	r1, r8
	mov	r0, r6
	bl	write_reg(PLT)
	cmp	r0, #0
	bne	.L113
	add	r8, r8, #1
	cmp	r8, #38
	bne	.L118
	mov	r2, #2
	vmov.f64	d0, d8
	mov	r1, r2
	mov	r0, r6
	str	r2, [r7]
	bl	write_reg(PLT)
	cmp	r0, #0
	bne	.L113
	mov	r3, #3
	add	r8, sp, #24
	str	r3, [r7]
	b	.L119
.L150:
	tst	r3, #1
	beq	.L149
.L119:
	vmov.f64	d0, d8
	mov	r2, r8
	mov	r1, #3
	mov	r0, r6
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L113
	ldr	r3, [sp, #24]
	tst	r3, #12
	beq	.L150
	mov	r0, #7
	b	.L113
.L148:
	bl	__stack_chk_fail(PLT)
.L149:
	and	r3, r3, #114
	cmp	r3, #114
	movne	r0, #5
	bne	.L113
	vmov.f64	d0, d8
	add	r2, sp, #28
	mov	r1, #6
	mov	r0, r6
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L113
	vmov.f64	d0, d8
	add	r2, sp, #32
	mov	r1, #7
	mov	r0, r6
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L113
	ldr	r2, [r4, #40]
	ldr	r3, [sp, #28]
	cmp	r2, r3
	bne	.L141
	ldr	r3, [sp, #32]
	cmp	r3, #2
	bne	.L141
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
	bne	.L113
	ldr	r3, [sp, #20]
	cmp	r3, #174
	bne	.L121
	ldr	r3, [sp, #784]
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
	bne	.L113
	bl	hm_now(PLT)
	vabs.f64	d7, d0
	vldr.64	d9, .L151
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bhi	.L121
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L121
	vcmpe.f64	d8, d0
	vmrs	APSR_nzcv, FPSCR
	movls	r0, #1
	bls	.L113
	mov	r3, #6
	vmov.f64	d0, d8
	mov	r2, #4
	mov	r1, #2
	mov	r0, r6
	str	r3, [r7]
	bl	write_reg(PLT)
	cmp	r0, #0
	bne	.L113
	mov	r3, #7
	vmov.f64	d0, d8
	mov	r2, r8
	mov	r1, #3
	mov	r0, r6
	str	r3, [r7]
	bl	read_reg(PLT)
	cmp	r0, #0
	bne	.L113
	ldr	r3, [sp, #24]
	tst	r3, #7
	movne	r0, #8
	bne	.L113
	bl	hm_now(PLT)
	vabs.f64	d7, d0
	vcmp.f64	d7, d9
	vmrs	APSR_nzcv, FPSCR
	bhi	.L121
	vcmpe.f64	d0, #0
	vmrs	APSR_nzcv, FPSCR
	bmi	.L121
	vcmpe.f64	d8, d0
	vmrs	APSR_nzcv, FPSCR
	movls	r0, #1
	movhi	r0, #0
	b	.L113
.L141:
	mov	r0, #4
	b	.L113
.L121:
	mov	r0, #3
	b	.L113
.L152:
	.align	3
.L151:
	.word	-1
	.word	2146435071
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC3+8)
	.word	__stack_chk_guard(GOT)
	.word	_GLOBAL_OFFSET_TABLE_-(.LPIC2+8)
	.size	hm_transact_sample, .-hm_transact_sample
	.ident	"GCC: (Ubuntu 11.2.0-19ubuntu1) 11.2.0"
	.section	.note.GNU-stack,"",%progbits
