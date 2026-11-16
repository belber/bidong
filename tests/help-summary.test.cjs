const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function loadPage(file, {wx = {}, api = {}, client = {decorate: () => ({}), stop() {}, refresh() {}}} = {}) {
  let page;
  const toasts = [];
  const env = Object.assign({showToast: o => toasts.push(o.title)}, wx);
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), {
    wx: env, Page: p => {page = p;},
    require: p => p.endsWith('/api') ? api : p.endsWith('/transcript') ? client :
      p.endsWith('/format') ? {formatDuration: v => String(v)} : p.includes('yuanbao') ?
        require('../miniprogram/utils/yuanbao') : {pageShare: {}}
  });
  page.setData = patch => Object.assign(page.data, patch);
  return {page, toasts};
}
const HELP = 'miniprogram/pages/help/help.js';
const DOCUMENT = 'miniprogram/pages/transcript/transcript.js';
const completed = (text = '第一句\n第二句') => ({status: 'completed', segments: text.split('\n').map((text, i) => ({start: i * 5, text}))});
function documentPage(options) {
  const loaded = loadPage(DOCUMENT, options);
  loaded.page.onTranscriptUpdate(completed());
  loaded.page.data.transcript = completed();
  return loaded;
}

test('帮助：六项问题默认收起，互斥展开，机器人受配置控制', async () => {
  const {page} = loadPage(HELP, {api: {getHelpConfig: async () => ({qq_group: ' 12345 '}), getPublicConfig: async () => ({robot_guide: true})}});
  await page.onLoad();
  assert.equal(page.data.faqs.length, 6);
  assert.equal(page.data.expandedFaq, '');
  assert.equal(page.data.robotExpanded, false);
  assert.equal(page.data.showRobotGuide, true);
  assert.equal(page.data.groupNo, '12345');
  assert.equal(page.data.showGroup, true);
  const tap = id => page.onToggleFaq({currentTarget: {dataset: {id}}});
  tap(page.data.faqs[0].id);
  tap(page.data.faqs[1].id);
  assert.equal(page.data.expandedFaq, page.data.faqs[1].id);
  tap(page.data.faqs[1].id);
  assert.equal(page.data.expandedFaq, '');
  page.onToggleRobot();
  assert.equal(page.data.robotExpanded, true);
});

test('帮助：群配置失败不影响机器人开关；空群号不复制', async () => {
  let copies = 0;
  const {page} = loadPage(HELP, {wx: {setClipboardData() {copies++;}}, api: {getHelpConfig: async () => {throw Error();}, getPublicConfig: async () => ({robot_guide: false})}});
  await page.onLoad();
  assert.equal(page.data.showGroup, false);
  assert.equal(page.data.showRobotGuide, false);
  page.onCopyGroup(); assert.equal(copies, 0);
});

test('帮助：机器人配置失败仍可复制群号，并提示复制失败', async () => {
  let value;
  const {page, toasts} = loadPage(HELP, {wx: {setClipboardData(o) {value = o.data; o.fail();}}, api: {getHelpConfig: async () => ({qq_group: '7654321'}), getPublicConfig: async () => {throw Error();}}});
  await page.onLoad();
  assert.equal(page.data.showRobotGuide, false);
  page.onCopyGroup();
  assert.equal(value, '7654321');
  assert.match(toasts[0], /复制失败/);
});

test('元宝：仅有效完成态自动复制，旧复制全文仍仅含正文', () => {
  let copies = [];
  const {page} = documentPage({wx: {setClipboardData(o) {copies.push(o.data); o.success();}}});
  page.onCopyText(); assert.equal(copies[0], '第一句\n第二句');
  page.onOpenSummary(); assert.equal(copies.length, 2); assert.equal(page.data.summaryVisible, true);
  page.onCloseSummary();
  for (const status of ['idle', 'queued', 'processing', 'no_speech', 'failed']) {
    page.onTranscriptUpdate({...completed(), status}); page.onOpenSummary();
    assert.equal(page.data.canSummarize, false); assert.equal(page.data.summaryVisible, false);
  }
  page.onTranscriptUpdate(completed('   ')); page.onOpenSummary();
  assert.equal(copies.length, 2);
});

test('元宝：点击后自动复制完整长文案，复制成功才显示确认框，不自动跳转', () => {
  let pending, copied, copies = 0, navigations = 0;
  const {page} = documentPage({wx: {
    setClipboardData(o) {pending = o; copied = o.data; copies++;},
    navigateToMiniProgram() {navigations++;}
  }});
  const long = '完整的长文案。'.repeat(20000);
  page.onTranscriptUpdate(completed(long)); page.onOpenSummary(); page.onOpenSummary();
  assert.equal(copies, 1); assert.equal(page.data.summaryCopying, true);
  assert.equal(page.data.summaryVisible, false);
  assert.equal(copied, '请总结以下视频文案，先用一句话概括核心内容，再分点列出重点，不补充原文没有的信息。\n\n' + long);
  pending.success();
  assert.equal(page.data.summaryVisible, true); assert.equal(page.data.summaryCopying, false);
  page.onOpenSummary(); assert.equal(copies, 1); assert.equal(navigations, 0);
});

test('元宝：复制失败不显示确认框、不跳转，可再次点击重试', () => {
  let pending, navigations = 0;
  const {page, toasts} = documentPage({wx: {setClipboardData(o) {pending = o;}, navigateToMiniProgram() {navigations++;}}});
  page.onOpenSummary(); pending.fail();
  assert.equal(page.data.summaryVisible, false); assert.equal(page.data.summaryCopying, false);
  assert.match(toasts.at(-1), /复制/);
  page.onOpenYuanbao(); assert.equal(navigations, 0);
  page.onOpenSummary(); pending.success(); assert.equal(page.data.summaryVisible, true);
});

test('元宝：取消仅关闭确认框，剪贴板不变；下次点击重新复制', () => {
  let clipboard = '', copies = 0;
  const {page} = documentPage({wx: {setClipboardData(o) {clipboard = o.data; copies++; o.success();}}});
  page.onOpenSummary(); const original = clipboard;
  page.onCloseSummary(); assert.equal(page.data.summaryVisible, false); assert.equal(clipboard, original);
  page.onOpenSummary(); assert.equal(copies, 2); assert.equal(page.data.summaryVisible, true);
});

test('元宝：离开、关闭或正文更新后迟到的复制回调不再弹框，保持原有状态', () => {
  for (const change of ['hide', 'close', 'text', 'status']) {
    let pending;
    const {page} = documentPage({wx: {setClipboardData(o) {pending = o;}}});
    page.data.tab = 'plain'; page.data.exportState = 'ready'; page.data.exportPath = '/local/file.txt';
    page.onOpenSummary();
    if (change === 'hide') {page.onHide(); page.onShow();}
    if (change === 'close') page.onCloseSummary();
    if (change === 'text') page.onTranscriptUpdate(completed('新正文'));
    if (change === 'status') page.onTranscriptUpdate({...completed(), status: 'failed'});
    pending.success();
    assert.equal(page.data.summaryVisible, false); assert.equal(page.data.summaryCopying, false);
    assert.equal(page.data.tab, 'plain'); assert.equal(page.data.exportState, 'ready');
    assert.equal(page.data.exportPath, '/local/file.txt');
  }
});

test('元宝：相同文案刷新不打断确认，确认点击内同步跳转，重复点击只发起一次', () => {
  let inClick = false, navigations = 0;
  const {page} = documentPage({wx: {setClipboardData(o) {o.success();}, navigateToMiniProgram(o) {
    assert.equal(inClick, true); assert.equal(o.appId, 'wxd5201eb08d2fa15c');
    assert.equal(o.envVersion, 'release'); assert.equal(o.path, undefined); assert.equal(o.extraData, undefined);
    navigations++;
  }}});
  page.onOpenSummary(); page.onTranscriptUpdate(completed()); assert.equal(page.data.summaryVisible, true);
  inClick = true; page.onOpenYuanbao(); page.onOpenYuanbao(); inClick = false;
  assert.equal(navigations, 1);
});

test('元宝：跳转成功或用户取消关闭确认框，不提示错误', () => {
  for (const result of ['success', 'cancel']) {
    let nav;
    const {page, toasts} = documentPage({wx: {setClipboardData(o) {o.success();}, navigateToMiniProgram(o) {nav = o;}}});
    page.onOpenSummary(); page.onOpenYuanbao();
    if (result === 'success') nav.success(); else nav.fail({errMsg: 'navigateToMiniProgram:fail cancel'});
    nav.complete();
    assert.equal(page.data.summaryVisible, false); assert.equal(page.data.summaryOpening, false);
    assert.equal(toasts.length, 0);
  }
});

test('元宝：真正失败或不支持跳转时保留已复制内容并提示搜索元宝', () => {
  for (const supported of [true, false]) {
    let nav, message, clipboard;
    const wx = {setClipboardData(o) {clipboard = o.data; o.success();}, showModal(o) {message = o;}};
    if (supported) wx.navigateToMiniProgram = o => {nav = o;};
    const {page} = documentPage({wx});
    page.onOpenSummary(); const original = clipboard; page.onOpenYuanbao();
    if (supported) {nav.fail({errMsg: 'navigateToMiniProgram:fail invalid appid'}); nav.complete();}
    assert.equal(page.data.summaryVisible, false); assert.equal(page.data.summaryOpening, false);
    assert.equal(clipboard, original); assert.match(message.content, /微信搜索/);
  }
});

test('配置与页面：保留目标配置，移除两步面板，仅保留复制成功后的确认框', () => {
  const app = JSON.parse(fs.readFileSync('miniprogram/app.json'));
  assert(app.navigateToMiniProgramAppIdList.includes('wx7564fd5313d24844'));
  assert(app.navigateToMiniProgramAppIdList.includes('wxd5201eb08d2fa15c'));
  assert.equal(JSON.parse(fs.readFileSync('miniprogram/pages/help/help.json')).navigationBarTitleText, '帮助与反馈');
  const markup = fs.readFileSync('miniprogram/pages/transcript/transcript.wxml', 'utf8');
  assert(markup.indexOf('summary-entry') < markup.indexOf('document-tabs'));
  assert(!markup.includes('summary-sheet')); assert(!markup.includes('onCopySummary'));
  assert(markup.includes('文案已复制')); assert(markup.includes('取消')); assert(markup.includes('前往元宝'));
  assert(markup.includes('bindtap="onOpenYuanbao"'));
});
