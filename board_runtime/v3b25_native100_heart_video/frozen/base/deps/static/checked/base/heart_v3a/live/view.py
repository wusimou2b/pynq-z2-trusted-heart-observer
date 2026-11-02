"""中文同拍显示；不访问硬件，不决定算法，不写结果文件。"""
from collections import deque
import html
import time

STATE_CN = {"created": "未启动", "preflight": "预检", "running": "运行中",
    "stopping": "正在停止", "stopped": "已停止", "faulted": "故障锁定",
    "shutdown_incomplete": "停止未完成"}
QUALITY_CN = {"good": "优", "medium": "中", "bad": "差"}
MOTION_CN = {"static": "静止", "light": "轻运动", "heavy": "强运动", "unknown": "待判断", None: "待判断"}
ROUTE_CN = {"none": "无输出", "raw": "原始", "mean": "四点均值", "nlms": "联合保护NLMS"}


def presentation(snapshot, *, now_ns):
    latest = snapshot.latest
    value = dict(state_cn=STATE_CN.get(snapshot.state, snapshot.state), sequence=None,
        bpm_text="N/A", historical=snapshot.state != "running", reason_cn="等待首帧",
        motion_cn="待判断", quality_cn="待判断", contact_cn="待判断", route_cn="无输出", mix=None)
    if latest is not None:
        frame = latest.runtime.frame
        age = now_ns - latest.saved.record.read_completed_ns
        value.update(sequence=frame.sequence, motion_cn=MOTION_CN.get(frame.motion, frame.motion),
            quality_cn=QUALITY_CN.get(frame.selected_quality, frame.selected_quality),
            contact_cn="正常" if frame.contact_ready else "异常／恢复中",
            route_cn=ROUTE_CN.get(frame.selected_route, frame.selected_route), mix=frame.nlms_mix,
            reason_cn=frame.reason_cn)
        if not 0 <= age <= 1_000_000_000:
            value.update(reason_cn="读取结果过期／时钟异常", historical=True)
        elif snapshot.state == "running" and snapshot.fault is None and frame.output_allowed and frame.bpm is not None:
            value["bpm_text"] = "{:.1f}".format(frame.bpm)
    if snapshot.state != "running":
        value["reason_cn"] = value["state_cn"] + "，曲线仅供历史查看"
    if snapshot.fault is not None:
        value.update(bpm_text="N/A", reason_cn="故障锁定：" + snapshot.fault.reason, historical=True)
    return value


class NotebookView:
    def __init__(self, *, clock=time):
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        fonts = {item.name for item in font_manager.fontManager.ttflist}
        candidate = next((name for name in ("Microsoft YaHei", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "SimHei") if name in fonts), None)
        with plt.rc_context({"font.family": candidate or "sans-serif", "axes.unicode_minus": False}):
            self.figure, self.axis = plt.subplots(figsize=(10, 3.5))
            self.axis.set_xlabel("时间（秒）")
            self.axis.set_ylabel("归一化PPG")
            self.lines = tuple(self.axis.plot([], [], label=label)[0] for label in
                ("原始去直流", "四点均值", "NLMS候选", "联合保护输出（非纯NLMS）"))
            self.axis.legend(loc="upper right")
        self.clock = clock
        self._last_refresh_ns = None
        self._figure_handle = self._text_handle = None
        self._samples = deque(maxlen=500)
        self._refreshes = self._errors = 0
        self._disabled = False
        self._error_text = ""

    def _render(self, snapshot, value):
        from IPython.display import display, HTML
        history = snapshot.history[-500:]
        times = [item.runtime.frame.time_s for item in history]
        for line, field in zip(self.lines, ("raw", "mean", "nlms_candidate", "joint_output")):
            line.set_data(times, [getattr(item.runtime.frame, field) for item in history])
        self.axis.relim()
        self.axis.autoscale_view()
        self.axis.set_title("历史曲线" if value["historical"] else "实时PPG（最多500点）")
        text = "状态：{state_cn}　序号：{sequence}　心率：{bpm_text}\n运动：{motion_cn}　质量：{quality_cn}　接触：{contact_cn}\n选路：{route_cn}　NLMS混合权重：{mix}\n{reason_cn}".format(**value)
        status = HTML("<pre>" + html.escape(text) + "</pre>")
        if self._figure_handle is None:
            self._figure_handle = display(self.figure, display_id=True)
            self._text_handle = display(status, display_id=True)
        else:
            self._figure_handle.update(self.figure)
            self._text_handle.update(status)

    def refresh(self, snapshot):
        now = self.clock.monotonic_ns()
        if self._disabled or self._last_refresh_ns is not None and now - self._last_refresh_ns < 500_000_000:
            return False
        self._last_refresh_ns = now
        try:
            value = presentation(snapshot, now_ns=now)
            self._render(snapshot, value)
            finished = self.clock.monotonic_ns()
            latest = snapshot.latest
            # 渲染完成也复核读取年龄；慢显示不能继续把过期数值标成当前BPM。
            if latest is not None and value["bpm_text"] != "N/A" and finished - latest.saved.record.read_completed_ns > 1_000_000_000:
                value = presentation(snapshot, now_ns=finished)
                self._render(snapshot, value)
                finished = self.clock.monotonic_ns()
            self._refreshes += 1
            if latest is not None:
                self._samples.append(dict(sequence=latest.runtime.frame.sequence, refresh_completed_ns=finished,
                    read_completed_ns=latest.saved.record.read_completed_ns,
                    read_to_display_ns=finished - latest.saved.record.read_completed_ns,
                    render_ns=finished - now, historical=value["historical"], bpm_text=value["bpm_text"]))
            return True
        except Exception as exc:
            self._errors += 1
            self._disabled, self._error_text = True, str(exc)
            return False

    def finish(self, snapshot):
        """显式结束查看并清N/A；不是一次实时刷新／延迟测量。"""
        value = presentation(snapshot, now_ns=self.clock.monotonic_ns())
        value.update(bpm_text="N/A", historical=True,
            reason_cn=value["reason_cn"] + "；查看结束，曲线仅供历史查看")
        if snapshot.state == "running":
            value["state_cn"] = "查看结束，正在请求停止"
        try:
            self._render(snapshot, value)
            return True
        except Exception as exc:
            self._errors += 1
            self._disabled, self._error_text = True, str(exc)
            return False

    def metrics(self):
        return dict(refreshes=self._refreshes, display_errors=self._errors, disabled=self._disabled,
            error=self._error_text, samples=[dict(item) for item in self._samples])

    def close(self):
        import matplotlib.pyplot as plt
        plt.close(self.figure)
