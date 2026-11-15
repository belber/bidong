const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');
const s=fs.readFileSync('miniprogram/pages/result/result.js','utf8');
test('视频入口回到完整CDN流且不申请准备任务',()=>{const body=s.slice(s.indexOf('  onUnifiedVideoTap(e)'),s.indexOf('  downloadPreparedVideo(state)'));assert(body.includes("kind:'watermarked'"));assert(!body.includes('api.prepareVideo'));assert(!s.includes('videoClient.start(this, api)'));});
