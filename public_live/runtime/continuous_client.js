(function(root,factory){
  const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;
  else root.ContinuousControl=api;
})(typeof window!=='undefined'?window:globalThis,function(){
  'use strict';
  class StopButton {
    constructor({button,status,heart,save,path,token,id}){
      Object.assign(this,{button,status,heart,save,path,token,id});this.submitted=false;this.finished=false;
      button.addEventListener('click',()=>this.submit());
    }
    async submit(){
      if(this.submitted||this.finished)return;
      this.submitted=true;this.button.disabled=true;
      this.heart.model.close();this.heart.view.paint();
      this.status.textContent='正在提交停止请求；当前心率已撤销，硬件停止尚未确认。';
      try{
        await this.save(this.path+'/request.json',{type:'file',format:'text',content:JSON.stringify({
          schema:'v3b25_manual_stop_request_v1',token:this.token,action:'stop',request_id:this.id(),
          client_submitted_wall_ms:Date.now()})});
        if(!this.finished)this.status.textContent='停止请求已提交；等待所有者完成收尾和导出，请勿中断内核或启动其它入口。';
      }catch(e){
        if(!this.finished)this.status.textContent='停止请求保存未确认：'+e.message+'；不能认定硬件停止，请保留页面，不要重复启动。';
      }
    }
    acceptState(state){
      if(!state||state.schema!=='v3b25_continuous_state_v1'||state.token!==this.token)return false;
      const phase=state.phase;
      if((phase==='stopped'||phase==='stopped_with_errors'||phase==='cancelled_before_start')
          &&state.cleanup_complete===true&&state.export_complete===true){
        this.finished=true;this.button.disabled=true;this.heart.model.close();this.heart.view.paint();
        this.status.textContent=phase==='stopped'?'已停止并导出：'+state.archive:
          phase==='cancelled_before_start'?'启动前已取消并导出；未启动硬件。':'已停止并导出，但存在故障／检查未通过，请回传结果。';
      }else if(phase==='stopping'||phase==='shutdown_incomplete'){
        this.heart.model.close();this.heart.view.paint();
        this.status.textContent=phase==='stopping'?'正在停止；等待真实硬件收尾和导出。':'停止未完成，保留所有权；请勿关闭内核或再次启动。';
      }else if(phase==='export_failed'){
        this.heart.model.close();this.heart.view.paint();
        this.status.textContent='结果导出失败；停止／导出未完整确认，请保留原目录和输出。';
      }else if(!this.submitted){
        this.status.textContent=phase==='running'?'持续采集中；首轮约3分钟后点击“正常停止并导出”。':'准备中；可提交停止请求，完成时间取决于当前底层调用。';
      }
      return true;
    }
  }
  function contentPath(options,notebookPath){
    if(options.relativeToNotebook!==true)return options.controlPath;
    const suffix=options.controlPath;
    if(typeof suffix!=='string'||!suffix||suffix.startsWith('/')||/[\\:]/.test(suffix)
        ||suffix.split('/').some(p=>!p||p==='.'||p==='..'))throw Error('invalid public control path');
    if(typeof notebookPath!=='string'||!notebookPath||notebookPath.startsWith('/')
        ||/[\\:]/.test(notebookPath)||notebookPath.split('/').some(p=>!p||p==='.'||p==='..'))
      throw Error('invalid public Notebook content path');
    const parts=notebookPath.split('/');parts.pop();
    return parts.concat(suffix.split('/')).join('/');
  }
  function boot(options){
    const element=document.getElementById(options.id),heart=HeartWave.boot(options);
    require(['base/js/namespace'],function(Jupyter){
      const path=contentPath(options,Jupyter.notebook.notebook_path);
      const c=new StopButton({button:element.querySelector('[data-stop]'),status:element.querySelector('[data-stop-status]'),
        heart,save:(path,doc)=>Jupyter.notebook.contents.save(path,doc),path,
        token:options.token,id:()=>options.token}); // Exactly one request per Python-issued random session.
      async function poll(){
        try{const d=await Jupyter.notebook.contents.get(path+'/state.json',{content:true});
          c.acceptState(typeof d.content==='string'?JSON.parse(d.content):d.content);
        }catch(e){if(!c.finished)element.querySelector('[data-stop-status]').textContent='控制状态回读失败；不能认定已停止。请保留页面：'+e.message;}
        if(!c.finished)setTimeout(poll,1000);
      }
      poll();
    });
    return heart;
  }
  return {StopButton,boot,contentPath};
});
