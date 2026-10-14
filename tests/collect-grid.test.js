// 收藏夹网格视图的结构契约：这次定稿的几条硬规则，防止后续被无意改回去。
// 页面渲染依赖微信开发者工具，这里只做文本级契约（与 page-metadata 的写法一致）。
const fs = require('fs');
const path = require('path');

const WXML = fs.readFileSync(path.join(__dirname, '../miniprogram/pages/collect/collect.wxml'), 'utf8');
const WXSS = fs.readFileSync(path.join(__dirname, '../miniprogram/pages/collect/collect.wxss'), 'utf8');
const JS = fs.readFileSync(path.join(__dirname, '../miniprogram/pages/collect/collect.js'), 'utf8');

describe('收藏夹网格视图契约', () => {
  test('网格容器按列数切换 class，列表分支走 wx:else', () => {
    expect(WXML).toContain('class="grid cols-{{cols}}" wx:if="{{view === \'grid\'}}"');
    expect(WXML).toContain('<block wx:else>');
  });

  test('三种列数都有对应样式', () => {
    expect(WXSS).toContain('.grid.cols-3');
    expect(WXSS).toContain('.grid.cols-4');
  });

  test('卡片上不再展示标签（列表、网格都不显示，标签只留给搜索）', () => {
    const gridStart = WXML.indexOf('class="grid cols-');
    const listStart = WXML.indexOf('<block wx:else>', gridStart);
    const gridBranch = WXML.slice(gridStart, listStart);

    expect(gridBranch).not.toContain('chip-tag');
    expect(WXML).not.toContain('chip-tag');
    expect(gridBranch).toContain('class="gsub"');
    expect(WXSS).not.toContain('.chips');
  });

  test('不再区分来源：没有来源角标、没有来源筛选分段', () => {
    expect(WXML).not.toContain('data-source=');
    expect(WXML).not.toContain('onSourceTap');
    expect(WXML).not.toContain('robot-records-tip');
    expect(WXML).not.toContain('>本机<');
    expect(WXML).not.toContain('>@壁咚咚<');
    expect(JS).not.toContain('sourceFilter');
  });

  test('平台角标保留（B站 / 抖音），列表与网格都有', () => {
    const gridStart = WXML.indexOf('class="grid cols-');
    const listStart = WXML.indexOf('<block wx:else>', gridStart);
    expect(WXML.slice(gridStart, listStart)).toContain('class="plat');
    expect(WXML.slice(listStart)).toContain('class="plat');
  });

  test('编辑态勾选圈不再和右上角平台角标打架（网格挪到左上角）', () => {
    const block = WXSS.slice(WXSS.indexOf('.gthumb .check'));
    expect(block.slice(0, block.indexOf('}'))).toContain('left: 8rpx');
    expect(WXSS).not.toContain('.src');
  });

  test('4 列只留标题，UP主/分区 也隐藏', () => {
    expect(WXSS).toContain('.grid.cols-4 .gsub');
  });

  test('网格与列表都能长按进编辑态（多选只有长按一个入口）', () => {
    const longPress = WXML.match(/bindlongpress="onCardLongPress"/g) || [];
    expect(longPress.length).toBe(2);
    expect(WXML).not.toContain('data-editbtn');
    expect(WXML).not.toContain('多选');
  });

  test('网格下广告是分组末尾的整行横幅，不是网格里的一格', () => {
    const gridStart = WXML.indexOf('class="grid cols-');
    const listStart = WXML.indexOf('<block wx:else>', gridStart);
    const gridBranch = WXML.slice(gridStart, listStart);

    expect(gridBranch).not.toContain('class="ad-slot gad"');
    expect(WXML).toContain('class="ad-slot ad-banner"');
    // 横幅贴在网格下方（分组边界上），所以不参与网格排版、也就不会空出半格
    expect(WXML.indexOf('class="ad-slot ad-banner"')).toBeGreaterThan(gridStart);
    expect(WXSS).not.toContain('grid-column: 1 / -1');
  });

  test('列数只由捏合调整：没有列数按钮，捏合事件挂在信息流上', () => {
    expect(WXML).not.toContain('data-cols=');
    expect(JS).not.toContain('onColsTap');
    expect(WXML).toContain('bindtouchstart="onFeedTouchStart"');
    expect(WXML).toContain('bindtouchmove="onFeedTouchMove"');
    expect(WXML).toContain('bindtouchend="onFeedTouchEnd"');
  });

  test('视图偏好通过 utils/viewPref 读写本地缓存', () => {
    expect(JS).toContain("require('../../utils/viewPref.js')");
    expect(JS).toContain('readPrefs()');
    expect(JS).toContain('savePrefs(');
  });
});
