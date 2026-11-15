const fs=require('fs');
const path=require('path');
const {loadPage}=require('./helpers/page');
const wxml=fs.readFileSync(path.join(__dirname,'../miniprogram/pages/result/result.wxml'),'utf8');
const PAGE=path.join(__dirname,'../miniprogram/pages/result/result.js');
const api=jest.requireActual('../miniprogram/utils/api');
const mockApi={resolveMediaUrl:api.resolveMediaUrl};
jest.mock('../miniprogram/utils/api',()=>mockApi);

test('reference cards use download/document icons and black semantic headings',()=>{
  expect(wxml).toContain('section-icon icon-download');
  expect(wxml).toContain('section-icon icon-document');
  const media=wxml.slice(wxml.indexOf('media-download-card'),wxml.indexOf('card transcript-card'));
  expect(media).toContain('media-item-icon icon-video');
  expect(media).toContain('media-item-icon icon-audio');
  expect(media).toContain('（{{mediaSize.video}}）');
  expect(media).not.toContain('class="bar"');
});

test('completed card shows success check, real language/duration and chevron',()=>{
  expect(wxml).toContain('transcript-status-icon');
  expect(wxml).toContain('识别语言：');
  expect(wxml).toContain('时长：{{durationText}}');
  expect(wxml).toContain('transcript-chevron');
  expect(wxml).not.toContain('transcript-badge');
});

test('completion metadata derives from real card and transcript, not mock reference duration',()=>{
  const {ctx}=loadPage(PAGE);
  ctx.applyResult({id:1,title:'视频',up_name:'作者',duration:624,media:{},tags:[],subtitles:[]});
  const state=require('../miniprogram/utils/transcript').decorate({status:'completed',language:'zh',segments:[]});
  ctx.onTranscriptUpdate(state);
  expect(ctx.data.durationText).toBe('10:24');
  expect(state.statusTitle).toBe('提取完成');
  expect(state.languageText).toBe('中文');
});

test('idle and processing presentation cannot show completed state',()=>{
  const {decorate}=require('../miniprogram/utils/transcript');
  expect(decorate().statusTitle).toBe('待提取');
  expect(decorate({status:'processing'}).statusTitle).toBe('提取中');
  expect(decorate({status:'no_speech'}).statusTitle).toBe('未检测到语音');
  expect(decorate({status:'completed',source:'platform',language:''}).languageText).toBe('');
});

test('successful state refresh clears stale network error text',async()=>{
  mockApi.getTranscript=jest.fn(()=>Promise.resolve({status:'completed',language:'zh',segments:[]}));
  const {ctx}=loadPage(PAGE);
  ctx.data.cardId=1;ctx.data.transcriptReadError='先前网络错误';
  ctx.onShow();await Promise.resolve();await Promise.resolve();
  expect(ctx.data.transcriptReadError).toBe('');
  ctx.onHide();
});

test('no-speech disabled action stays short enough for compact pill',()=>{
  const state=require('../miniprogram/utils/transcript').decorate({status:'no_speech'});
  expect(state.button).toBe('无语音');
});

test('closed download switches show an explicit empty state instead of a bare card',()=>{
 const {ctx}=loadPage(PAGE);
 ctx.applyResult({id:1,platform:'bilibili',title:'视频',media:{watermarked:false,clean:false,audio:false},tags:[],subtitles:[]});
 expect(ctx.data.hasMediaDownloads).toBe(false);
 expect(wxml).toContain('media-empty');
 ctx.applyResult({id:1,platform:'bilibili',title:'视频',media:{watermarked:true,audio:true},tags:[],subtitles:[]});
 expect(ctx.data.hasMediaDownloads).toBe(true);
});
