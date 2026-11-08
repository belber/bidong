// 方式 2 的三步引导：关注 → 评论 @ → 进收藏夹；示例只保留「我 @壁咚咚私藏」。
const fs = require('fs');
const path = require('path');

const read = (rel) => fs.readFileSync(path.join(__dirname, '../miniprogram', rel), 'utf8');

const PAGES = [
  ['首页', 'pages/home/home.wxml'],
  ['收藏夹', 'pages/collect/collect.wxml']
];

describe.each(PAGES)('%s的 @壁咚咚私藏 引导', (_name, file) => {
  const wxml = () => read(file);

  test('三步文案齐全', () => {
    const text = wxml();
    expect(text).toContain('关注B站用户 壁咚咚私藏');
    expect(text).toContain('评论 @壁咚咚私藏');
    expect(text).toContain('进收藏夹');
  });

  test('写明仅支持 B站', () => {
    expect(wxml()).toContain('仅支持 B站');
  });

  test('只保留评论示例，不再有视频卡片图例', () => {
    const text = wxml();
    expect(text).toContain('demo-comment');
    expect(text).toContain('@壁咚咚私藏');
    expect(text).not.toContain('demo-video');
    expect(text).not.toContain('一口气看懂《三体》');
  });
});

describe.each(PAGES)('%s引导的单行样式', (_name, file) => {
  const wxss = () => read(file.replace('.wxml', '.wxss'));

  test('步骤是单行 flex，不再三行堆叠', () => {
    const css = wxss();
    const rule = css.slice(css.indexOf('.guide-steps {'), css.indexOf('}', css.indexOf('.guide-steps {')));
    expect(rule).toContain('display: flex');
    expect(rule).toContain('flex-wrap: nowrap');
    expect(css).toContain('.guide-step .n');
  });
});
