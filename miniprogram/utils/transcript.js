const api = require('./api');
const LABELS = {
  idle: ['按需提取', '提取文案'], queued: ['排队中，可稍后回来查看', '排队中'],
  processing: ['正在提取，可离开页面稍后查看', '提取中'], completed: ['提取完成', '查看文案'],
  no_speech: ['未检测到明显语音，可能是纯音乐或声音较小', '无语音'], failed: ['提取未完成', '重试']
};
const STATUS_TITLES = {idle:'待提取',queued:'排队中',processing:'提取中',completed:'提取完成',no_speech:'未检测到语音',failed:'提取未完成'};
const STATUS_HINTS = {idle:'适用于口播、讲解视频',queued:'可离开页面，稍后回来查看',processing:'可离开页面，稍后回来查看',no_speech:'可能是纯音乐或声音较小',failed:'请稍后重试'};
const LANGUAGES = {zh:'中文','zh-cn':'中文','zh-hans':'中文','ai-zh':'中文',en:'英语',ja:'日语',ko:'韩语',yue:'粤语'};
function decorate(result) {
  const value = result || {status:'idle',segments:[]};
  const labels = LABELS[value.status] || LABELS.failed;
  const language = String(value.language || '').toLowerCase();
  return Object.assign({}, value, {statusTitle:STATUS_TITLES[value.status] || STATUS_TITLES.failed,
    statusHint:value.error || STATUS_HINTS[value.status] || '',
    languageText:LANGUAGES[language] || (language && language !== 'auto' ? value.language : ''),label: value.error || labels[0], button: labels[1],
    busy: value.status === 'queued' || value.status === 'processing'});
}
function stop(page) {
  page._transcriptVisible = false;
  page._transcriptEpoch = (page._transcriptEpoch || 0)+1;
  clearTimeout(page._transcriptTimer);
}
function apply(page, value) {
  const state = decorate(value);
  page.setData({transcript:state,transcriptReadError:''});
  if (page.onTranscriptUpdate) page.onTranscriptUpdate(state);
}
function refresh(page) {
  clearTimeout(page._transcriptTimer);
  const id = page.data.cardId;
  if (!page._transcriptVisible || !id || page.data.publicView || page.data.isNote || !api.getTranscript) return Promise.resolve();
  const epoch = page._transcriptEpoch || 0;
  return api.getTranscript(id).then(value => {
    if (!page._transcriptVisible || epoch !== (page._transcriptEpoch || 0) || id !== page.data.cardId) return;
    apply(page,value);
    if (page.data.transcript.busy) page._transcriptTimer = setTimeout(() => refresh(page),3000);
  }).catch(error => {
    if (!page._transcriptVisible || epoch !== (page._transcriptEpoch || 0) || id !== page.data.cardId) return;
    page.setData({transcriptReadError:error.message || '暂时无法查询文案'});
    // Preserve a running job on transient network failures; never submit from polling.
    if (page.data.transcript.busy) page._transcriptTimer = setTimeout(() => refresh(page),3000);
  });
}
function start(page) {
  if (page._transcriptSubmitting || !page.data.cardId || page.data.publicView || page.data.isNote || page.data.transcript.busy) return Promise.resolve();
  page._transcriptEpoch=(page._transcriptEpoch || 0)+1;
  page._transcriptSubmitting=true;
  page.setData({transcriptSubmitting:true,transcriptReadError:''});
  const id=page.data.cardId;
  return api.startTranscript(id).then(value => {
    if (id !== page.data.cardId) return;
    apply(page,value);
    if(page._transcriptVisible && page.data.transcript.busy) {
      clearTimeout(page._transcriptTimer);
      page._transcriptTimer=setTimeout(() => refresh(page),3000);
    }
  }).catch(error => {
    if(id === page.data.cardId) wx.showToast({title:error.message || '暂时无法提取',icon:'none'});
  }).finally(() => {page._transcriptSubmitting=false;page.setData({transcriptSubmitting:false});});
}
module.exports={decorate,stop,refresh,start};
