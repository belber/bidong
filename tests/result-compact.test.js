const fs=require('fs');const path=require('path');
const xml=fs.readFileSync(path.join(__dirname,'../miniprogram/pages/result/result.wxml'),'utf8');
const css=fs.readFileSync(path.join(__dirname,'../miniprogram/pages/result/result.wxss'),'utf8');
test('default media explanation removed and video uses the current direct-download flow',()=>{
 expect(xml).not.toContain('无水印 · 保留原声');
 expect(xml).not.toContain('准备中，可稍后回来');
 expect(xml).not.toContain('videoPreparation.error');
 expect(xml).toContain('bindtap="onUnifiedVideoTap"');
 expect(xml).toContain("{{downloading && (activeKind === 'video' || activeKind === 'watermarked')}}");
});
test('transcript title and action share compact header; idle status row is not rendered',()=>{
 const header=xml.match(/<view class="transcript-header">([\s\S]*?)<\/button>\s*<\/view>/);
 expect(header).not.toBeNull();expect(header[1]).toContain('视频文案');expect(header[1]).toContain('bindtap="onTranscriptTap"');
 expect(xml).toContain('class="transcript-action-row" wx:if="{{transcript.status !== \'idle\' || transcriptSubmitting}}"');
 expect(css).toContain('.transcript-card .section-heading { margin-bottom: 0; }');
});
test.each([['idle','提取文案'],['queued','排队中'],['processing','提取中'],['completed','查看文案'],['no_speech','无语音'],['failed','重试']])('state %s keeps correct action %s',(status,button)=>{
 const {decorate}=require('../miniprogram/utils/transcript');const state=decorate({status,segments:[]});expect(state.button).toBe(button);
 if(['failed','no_speech'].includes(status))expect(state.statusHint).toBeTruthy();
});
