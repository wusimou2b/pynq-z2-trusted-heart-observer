"""Bounded, incremental SVG candidate. No acquisition or publication permission logic."""
import html
import math

SERIES = (('raw','原始去直流','#3578c4'),('mean','两点均值（25Hz）','#e28a24'),
          ('nlms_candidate','NLMS候选','#8a64b8'),('joint_output','联合保护输出（非纯NLMS）','#1c9275'))


class CachedSvgBuilder:
    """Cache only curve coordinates; always rebuild the caller's current status text."""

    def __init__(self):
        self._cache = {}
        self._anchor = None
        self._hits = self._encoded = self._rebases = 0

    def cache_stats(self):
        return dict(cache_size=len(self._cache), hits=self._hits,
                    encoded=self._encoded, rebases=self._rebases)

    def build_html(self, snapshot, value):
        frames = [item.runtime.frame for item in snapshot.history[-500:]]
        entries, next_cache = [], {}
        times, lows, highs = [], [], []
        for frame in frames:
            signature = (frame.sequence, frame.time_s, frame.raw, frame.mean,
                         frame.nlms_candidate, frame.joint_output)
            entry = self._cache.get(frame.sequence)
            if entry is not None and entry[0] == signature:
                self._hits += 1
            else:
                finite = [v for v in signature[2:] if v is not None and math.isfinite(v)]
                entry = [signature, min(finite) if finite else None,
                         max(finite) if finite else None, None]
            times.append(frame.time_s)
            if entry[1] is not None:
                lows.append(entry[1]); highs.append(entry[2])
            entries.append(entry)
            next_cache[frame.sequence] = entry
        xmin,xmax = (min(times),max(times)) if times else (0.,1.)
        ymin,ymax = (min(lows),max(highs)) if lows else (-1.,1.)
        dx,dy = max(xmax-xmin,.04),max(ymax-ymin,1e-9)
        rebase = self._anchor is None
        if self._anchor is not None:
            ox,oy,ux,uy = self._anchor
            rebase = not (.25 <= 900*ux/dx <= 4 and .25 <= 210*uy/dy <= 4)
            # Limit cancellation when a new history uses a distant time/value origin.
            rebase |= abs(ox-xmin)/dx > 1024 or abs(oy-ymin)/dy > 1024
        if rebase:
            self._rebases += int(self._anchor is not None)
            self._anchor = (xmin,ymin,dx/900,dy/210)
        ox,oy,ux,uy = self._anchor
        for entry in entries:
            if rebase or entry[3] is None:
                signature = entry[0]
                x = (signature[1]-ox)/ux
                entry[3] = tuple('L{:.3f},{:.3f}'.format(x,(y-oy)/uy)
                    if y is not None and math.isfinite(y) else '|' for y in signature[2:])
                self._encoded += 1
        self._cache = next_cache
        paths = []
        for index,(key,_,color) in enumerate(SERIES):
            # The marker converts the first valid point after every gap to M.
            commands = ('|'+''.join(entry[3][index] for entry in entries)).replace('|L','M').replace('|','')
            paths.append('<path data-series="{}" d="{}" fill="none" stroke="{}" '
                         'stroke-width="1.5" vector-effect="non-scaling-stroke"/>'.format(key,commands,color))
        matrix = '{:.17g} 0 0 {:.17g} {:.17g} {:.17g}'.format(
            900*ux/dx,-210*uy/dy,45+900*(ox-xmin)/dx,235-210*(oy-ymin)/dy)
        text = ('状态：{state_cn}　序号：{sequence}　心率：{bpm_text}\n'
                '运动：{motion_cn}　质量：{quality_cn}　接触：{contact_cn}\n'
                '选路：{route_cn}　NLMS混合权重：{mix}\n{reason_cn}').format(**value)
        legend = '　'.join('<span style="color:{}">● {}</span>'.format(color,label) for _,label,color in SERIES)
        title = '历史曲线' if value['historical'] else '实时PPG（25Hz处理）'
        return ('<section style="font-family:sans-serif;max-width:1000px">'
            '<pre style="white-space:pre-wrap;font-size:15px">'+html.escape(text)+'</pre>'
            '<div>'+legend+'</div><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 280" '
            'role="img" aria-label="PPG历史波形" data-points="{}" data-first-sequence="{}">'.format(
                len(frames),frames[0].sequence if frames else '')+
            '<rect width="1000" height="280" fill="#fafbfc"/>'
            '<text x="45" y="17" font-size="13">'+title+' · 归一化PPG</text>'+
            '<g transform="matrix('+matrix+')">'+''.join(paths)+'</g>'+
            '<text x="45" y="260" font-size="12">{:.2f} 秒</text>'.format(xmin)+
            '<text x="900" y="260" font-size="12">{:.2f} 秒</text>'.format(xmax)+
            '</svg><p style="font-size:12px;color:#555">请核对序号持续更新；暂停/断连即历史，不能作为当前心率。'
            '原始50Hz / 处理25Hz；显示约2次/秒。非医疗用途。</p></section>')
