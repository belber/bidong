const path = require('path');
const {loadPage} = require('./helpers/page');
const mockApi = {
  resolveMediaUrl: x => x,
  getTranscript: jest.fn(() => Promise.resolve({status:'idle',segments:[]})),
  startTranscript: jest.fn(() => Promise.resolve({status:'queued',segments:[]})),
  transcriptExport: jest.fn(() => Promise.resolve({url:'https://api.test/file',header:{}}))
};
jest.mock('../miniprogram/utils/api', () => mockApi);
const RESULT = path.join(__dirname,'../miniprogram/pages/result/result.js');
const TRANSCRIPT = path.join(__dirname,'../miniprogram/pages/transcript/transcript.js');
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };

beforeEach(() => {jest.useFakeTimers();jest.clearAllMocks();});
afterEach(() => {jest.clearAllTimers();jest.useRealTimers();});

test('entering result never submits ASR; more info defaults collapsed', async () => {
  const {ctx}=loadPage(RESULT);
  ctx.applyResult({id:1,title:'跳舞',media:{},subtitles:[],tags:[]});
  ctx.onShow(); await flush();
  expect(ctx.data.moreInfoExpanded).toBe(false);
  expect(mockApi.startTranscript).not.toHaveBeenCalled();
  ctx.onToggleMoreInfo(); expect(ctx.data.moreInfoExpanded).toBe(true);
  ctx.onHide();
});

test('click submits once and hidden page stops polling', async () => {
  const {ctx}=loadPage(RESULT);
  ctx.data.cardId=1;
  ctx.onShow(); await flush();
  ctx.onTranscriptTap(); ctx.onTranscriptTap(); await flush();
  expect(mockApi.startTranscript).toHaveBeenCalledTimes(1);
  ctx.onHide(); const calls=mockApi.getTranscript.mock.calls.length;
  jest.advanceTimersByTime(9000); await flush();
  expect(mockApi.getTranscript).toHaveBeenCalledTimes(calls);
});

test('public view and image notes cannot enqueue', () => {
  const {ctx}=loadPage(RESULT);
  ctx.data.cardId=1;ctx.data.publicView=true;ctx.onTranscriptTap();
  ctx.data.publicView=false;ctx.data.isNote=true;ctx.onTranscriptTap();
  expect(mockApi.startTranscript).not.toHaveBeenCalled();
});

test('transcript page copies plain text and exposes timeline', async () => {
  mockApi.getTranscript.mockResolvedValueOnce({status:'completed',source:'asr',language:'zh',segments:[{start:3.2,end:5.1,text:'你好。'},{start:8,end:9,text:'再见。'}]});
  const {ctx,clipboard}=loadPage(TRANSCRIPT);
  ctx.onLoad({id:'5',title:encodeURIComponent('口播'),author:encodeURIComponent('作者'),duration:'10'});
  ctx.onShow();await flush();
  expect(ctx.data.lines[0].timeText).toBe('00:03');
  ctx.onCopyText();expect(clipboard).toEqual(['你好。\n再见。']);
  ctx.onHide();
});
