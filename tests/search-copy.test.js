// 搜一搜关键词：名称改不了，就用页面标题 + 可见文案承接「视频下载」这类搜索词。
const fs = require('fs');
const path = require('path');

const read = (rel) => fs.readFileSync(path.join(__dirname, '../miniprogram', rel), 'utf8');
const title = (page) => JSON.parse(read(`pages/${page}/${page}.json`)).navigationBarTitleText || '';

describe('页面标题覆盖搜索词', () => {
  test('首页标题覆盖 B站/抖音视频下载 + 视频提取', () => {
    expect(title('home')).toContain('B站视频下载');
    expect(title('home')).toContain('抖音视频下载');
    expect(title('home')).toContain('视频下载');
    expect(title('home')).toContain('视频提取');
  });

  test('帮助页覆盖 B站/抖音视频提取，收藏和结果页覆盖视频下载', () => {
    expect(title('help')).toContain('B站视频提取');
    expect(title('help')).toContain('抖音视频提取');
    expect(title('help')).toContain('视频下载');
    expect(title('collect')).toContain('视频下载');
    expect(title('result')).toContain('视频下载');
  });

  test('关于页标题覆盖视频下载 / 视频提取两个泛词', () => {
    expect(title('about')).toContain('视频下载');
    expect(title('about')).toContain('视频提取');
  });
});

describe('页面可见文案', () => {
  test('首页按钮副标题和提示里出现「视频下载 / 保存」', () => {
    const wxml = read(`pages/home/home.wxml`);
    expect(wxml).toContain('视频下载与提取');
    expect(wxml).toContain('下载、提取视频');
  });

  test('帮助页有「下载视频」和抖音下载的问答', () => {
    const wxml = read(`pages/help/help.wxml`);
    expect(wxml).toContain('怎么提取视频？');
    expect(wxml).toContain('支持抖音视频下载吗？');
    expect(wxml).toContain('怎么提取抖音视频？');
  });

  test('关于页有公开的「能做什么」文案（可被搜一搜索引）', () => {
    const wxml = read(`pages/about/about.wxml`);
    expect(wxml).toContain('能做什么');
    expect(wxml).toContain('B站视频下载');
    expect(wxml).toContain('抖音视频下载');
  });
});
