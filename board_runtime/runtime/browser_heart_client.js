(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.HeartWave = api;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  class HeartModel {
    constructor() {
      this.rows=[]; this.packet=null; this.index=-1; this.offsetUpper=null;
      this.visible=true; this.minIssued=-Infinity; this.ended=false;
    }
    synchronize(sent, server, received) {
      if (![sent,server,received].every(Number.isFinite) || received<sent || received-sent>250)
        throw new Error('browser clock handshake failed');
      // The server timestamp lies after client send and before client receive.
      // Using the upper offset makes delayed delivery consume its true lease.
      this.offsetUpper=server-sent;
    }
    receive(packet, now) {
      if (!Number.isInteger(packet.index) || packet.index<=this.index) return false;
      const curves=packet.curves;
      if (!curves || !Array.isArray(curves.rows) || curves.rows.length>500)
        throw new Error('invalid bounded curve packet');
      const next=curves.reset?[]:this.rows.slice();
      for (const row of curves.rows) {
        if (!Array.isArray(row)||row.length!==6||!Number.isInteger(row[0])||row[0]<0 ||
            !Number.isFinite(row[1])||row.slice(2).some(v=>v!==null&&!Number.isFinite(v)))
          throw new Error('invalid curve row');
        if (next.length && row[0]!==next[next.length-1][0]+1) throw new Error('curve sequence gap');
        next.push(row.slice());
      }
      if (next.length && next[next.length-1][0]!==curves.last) throw new Error('curve endpoint mismatch');
      this.rows=next.slice(-500); this.packet=packet; this.index=packet.index; this.receivedAt=now;
      if (packet.ended) this.ended=true;
      return true;
    }
    setVisible(value, now) {
      this.visible=value;
      if (value && this.offsetUpper!==null) this.minIssued=now+this.offsetUpper;
    }
    close() {this.ended=true;}
    current(now) {
      const p=this.packet;
      const upper=this.offsetUpper===null?NaN:now+this.offsetUpper;
      const age=p?upper-p.read_ms:NaN;
      const fresh=!!p && this.offsetUpper!==null && this.visible && !this.ended &&
        p.state==='running' && p.eligible===true && p.historical===false &&
        Number.isFinite(p.read_ms) && Number.isFinite(p.issued_ms) &&
        p.issued_ms>=this.minIssued && upper>=p.issued_ms && upper-p.issued_ms<=1000 &&
        age>=0 && age<=1000 && /^\d+(\.\d)?$/.test(p.bpm_text);
      return {bpm_text:fresh?p.bpm_text:'N/A',historical:!fresh,status:p?p.status:{},
        message:this.ended?'查看结束，曲线仅供历史查看':
          !this.visible?'页面隐藏；等待新状态':fresh?'当前值':'等待当前有效心率／数据已过期'};
    }
  }

  function attach(element, model) {
    const status=element.querySelector('[data-status]');
    const note=element.querySelector('[data-note]');
    const canvas=element.querySelector('canvas'), ctx=canvas.getContext('2d');
    const colors=['#4b83d1','#df9b22','#5aaf79','#cf5774'];
    function paint() {
      const value=model.current(performance.now()), s=value.status;
      status.textContent=`状态：${s.state_cn||'准备显示'}　序号：${s.sequence??'—'}　心率：${value.bpm_text}\n`+
        `运动：${s.motion_cn||'待判断'}　质量：${s.quality_cn||'待判断'}　接触：${s.contact_cn||'待判断'}\n`+
        `选路：${s.route_cn||'无输出'}　NLMS混合权重：${s.mix??'—'}`;
      note.textContent=value.message+(s.reason_cn?'；'+s.reason_cn:'');
      ctx.clearRect(0,0,canvas.width,canvas.height);
      ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);
      const rows=model.rows;
      if(!rows.length)return;
      const times=rows.map(r=>r[1]);const x0=times[0], x1=Math.max(x0+.04,times[times.length-1]);
      let lo=Infinity,hi=-Infinity;
      for(const r of rows)for(let j=2;j<6;j++)if(r[j]!==null){lo=Math.min(lo,r[j]);hi=Math.max(hi,r[j]);}
      if(!Number.isFinite(lo))return;
      const pad=Math.max((hi-lo)*.1,.001);lo-=pad;hi+=pad;
      const w=canvas.width-48,h=canvas.height-36;
      ctx.strokeStyle='#e5e8ed';ctx.lineWidth=1;
      for(let n=0;n<=4;n++){let y=12+h*n/4;ctx.beginPath();ctx.moveTo(36,y);ctx.lineTo(36+w,y);ctx.stroke();}
      for(let j=2;j<6;j++){
        let open=false;ctx.beginPath();ctx.strokeStyle=colors[j-2];ctx.lineWidth=1.5;
        for(const r of rows){if(r[j]===null){open=false;continue;}
          const x=36+(r[1]-x0)/(x1-x0)*w,y=12+(hi-r[j])/(hi-lo)*h;
          if(open)ctx.lineTo(x,y);else ctx.moveTo(x,y);open=true;}
        ctx.stroke();
      }
      ctx.fillStyle='#555';ctx.font='12px sans-serif';
      ctx.fillText(x0.toFixed(1)+'s',36,canvas.height-6);
      ctx.fillText(x1.toFixed(1)+'s',canvas.width-60,canvas.height-6);
    }
    const timer=setInterval(paint,100);
    const visibility=()=>{model.setVisible(!document.hidden,performance.now());paint();};
    document.addEventListener('visibilitychange',visibility);
    paint();
    return {paint,dispose(){clearInterval(timer);document.removeEventListener('visibilitychange',visibility);model.close();paint();}};
  }

  function boot(options) {
    const element=document.getElementById(options.id);
    if(!element)throw new Error('browser waveform element missing');
    const model=new HeartModel(), view=attach(element,model);
    const ready=element.querySelector('[data-ready]');
    require(['base/js/namespace'],function(Jupyter){
      const sent=performance.now();
      const comm=Jupyter.notebook.kernel.comm_manager.new_comm(options.target,{kind:'sync',client_sent_ms:sent});
      comm.on_msg(function(msg){
        try{
          const p=msg.content.data;
          if(p.kind==='sync'){
            const received=performance.now();model.synchronize(p.client_sent_ms,p.server_ms,received);
            comm.send({kind:'ready',client_sent_ms:p.client_sent_ms,client_received_ms:received,server_ms:p.server_ms});
            ready.textContent='浏览器绘图已就绪，可以运行第二单元';ready.style.color='#187743';
          }else if(p.kind==='frame'){model.receive(p,performance.now());view.paint();}
        }catch(e){model.close();ready.textContent='显示故障：'+e.message;view.paint();}
      });
      comm.on_close(function(){view.dispose();ready.textContent='查看已结束';});
    });
    return {model,view};
  }
  return {HeartModel,attach,boot};
});
