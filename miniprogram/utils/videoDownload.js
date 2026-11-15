const ACTIVE = ['queued', 'processing'];
function size(n) { return n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.ceil(n / 1024) + ' KB'; }
function apply(page, state) {
  const patch = {videoPreparation:state, videoPreparing:ACTIVE.includes(state.status), videoReadError:''};
  const bytes = state.size_bytes || state.estimated_size;
  if (bytes) patch.mediaSize = Object.assign({},page.data.mediaSize,{video:(state.size_bytes ? '' : '约 ') + size(bytes)});
  page.setData(patch);
}
function stop(page) { page._videoVisible=false; page._videoEpoch=(page._videoEpoch||0)+1; clearTimeout(page._videoTimer); }
function start(page,api) {
  stop(page); page._videoVisible=true;
  if (!page.data.cardId || page.data.isDouyin || page.data.publicView || !page.data.media || !page.data.media.clean || !api.videoPreparation) return;
  const id=page.data.cardId, epoch=page._videoEpoch;
  const current=()=>page._videoVisible && page._videoEpoch===epoch && page.data.cardId===id;
  const poll=()=>api.videoPreparation(id).then(state=>{
    if(!current())return;
    // Direct CDN results are not persisted as server tasks.
    if(state.status==='idle' && page.data.videoPreparation && page.data.videoPreparation.mode==='direct')return;
    apply(page,state);
    if(ACTIVE.includes(state.status))page._videoTimer=setTimeout(poll,3000);
  }).catch(err=>{
    if(!current())return;
    page.setData({videoReadError:err.message||'准备状态查询失败，点击重试'});
    if(page.data.videoPreparing)page._videoTimer=setTimeout(poll,5000);
  });
  poll();
}
module.exports={start,stop,apply};
