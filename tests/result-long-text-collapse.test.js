// 标签、简介很长时默认折叠成两行，点「展开」再看全文，保证结果页干净。
const fs = require('fs');
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const PAGE = path.join(__dirname, '../miniprogram/pages/result/result.js');
const WXML = fs.readFileSync(
  path.join(__dirname, '../miniprogram/pages/result/result.wxml'), 'utf8'
);

const CARD = {
  id: 1,
  bvid: 'BV1xx411c7mD',
  title: '标题',
  up_name: 'UP主',
  partition: '知识',
  pubdate: 0,
  cover_url: '',
  desc: '',
  source_url: '',
  stats: {},
  tags: [],
  media: {},
  subtitles: [],
  features: {}
};

const toggle = (ctx, field) => ctx.onToggleField({ currentTarget: { dataset: { field } } });

describe('标签 / 简介折叠', () => {
  test('长内容默认折叠，可以展开再收起', () => {
    const { ctx } = loadPage(PAGE);
    ctx.applyResult({
      ...CARD,
      tags: ['标签一', '标签二', '标签三', '标签四', '标签五', '标签六', '标签七', '标签八'],
      desc: '这是一段很长的简介，'.repeat(6)
    });

    expect(ctx.data.tagsLong).toBe(true);
    expect(ctx.data.descLong).toBe(true);
    expect(ctx.data.tagsExpanded).toBe(false);
    expect(ctx.data.descExpanded).toBe(false);

    toggle(ctx, 'tags');
    toggle(ctx, 'desc');
    expect(ctx.data.tagsExpanded).toBe(true);
    expect(ctx.data.descExpanded).toBe(true);

    toggle(ctx, 'tags');
    expect(ctx.data.tagsExpanded).toBe(false);
  });

  test('短内容不显示展开按钮', () => {
    const { ctx } = loadPage(PAGE);
    ctx.applyResult({ ...CARD, tags: ['科幻'], desc: '很短的简介' });

    expect(ctx.data.tagsLong).toBe(false);
    expect(ctx.data.descLong).toBe(false);
  });

  test('模板里是两行截断 + 展开/复制操作', () => {
    expect(WXML).toContain('clamp-2');
    expect(WXML).toContain('bindtap="onToggleField" data-field="tags"');
    expect(WXML).toContain('bindtap="onToggleField" data-field="desc"');
    expect(WXML).toContain('{{tagsExpanded ? \'收起\' : \'展开\'}}');
    expect(WXML).toContain('{{descExpanded ? \'收起\' : \'展开\'}}');
  });
});
