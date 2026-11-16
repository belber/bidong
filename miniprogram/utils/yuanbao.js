// 仅负责跳转前的文案准备；不调用模型，也不向目标小程序传递内容。
const APP_ID = 'wxd5201eb08d2fa15c';
const PROMPT = '请总结以下视频文案，先用一句话概括核心内容，再分点列出重点，不补充原文没有的信息。';
function summaryText(text) { return PROMPT + '\n\n' + text; }
module.exports = {APP_ID, summaryText};
