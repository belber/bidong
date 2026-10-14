// 来源筛选去掉之后：收藏夹不再按来源过滤，未绑定的引导卡改挂在「空收藏夹」上。
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const COLLECT = path.join(__dirname, '../miniprogram/pages/collect/collect.js');

function card(id, source, title) {
  return {
    id,
    bvid: 'BV' + id,
    source,
    title: title || '标题' + id,
    month: '2026-10',
    collected_at: id,
    duration: 61,
    cover_url: '/media/covers/BV' + id + '.jpg',
    tags: [],
    partition: '知识',
    up_name: '某UP'
  };
}

describe('收藏夹引导卡', () => {
  test('未绑定且一张卡都没有 → 显示引导', () => {
    const { ctx } = loadPage(COLLECT);
    ctx.setData({ isBound: false, cards: [] });
    ctx.rebuild();
    expect(ctx.data.showRobotGuide).toBe(true);
  });

  test('已绑定且没有卡 → 走普通空态，不显示引导', () => {
    const { ctx } = loadPage(COLLECT);
    ctx.setData({ isBound: true, cards: [] });
    ctx.rebuild();
    expect(ctx.data.showRobotGuide).toBe(false);
  });

  test('未绑定但已经有卡片 → 不显示引导（不挡着收藏）', () => {
    const { ctx } = loadPage(COLLECT);
    ctx.setData({ isBound: false, cards: [card(1, 'local')] });
    ctx.rebuild();
    expect(ctx.data.showRobotGuide).toBe(false);
  });

  test('不再按来源过滤：本机与 @壁咚咚 的卡片一起出现', () => {
    const { ctx } = loadPage(COLLECT);
    ctx.setData({ isBound: true, cards: [card(1, 'local'), card(2, 'robot')] });
    ctx.rebuild();
    // collected_at 倒序 → 2 在前；卡片不足 5 张时末尾会补一条广告，按 id 取卡片即可
    expect(ctx.data.groups[0].items.filter((i) => !i.isAd).map((i) => i.id)).toEqual([2, 1]);
  });

  test('搜索仍然生效（去掉的只是来源这一维）', () => {
    const { ctx } = loadPage(COLLECT);
    ctx.setData({ isBound: true, cards: [card(1, 'local', '三体解析'), card(2, 'robot', '深度学习入门')] });
    ctx.setData({ keyword: '深度' });
    ctx.rebuild();
    expect(ctx.data.groups[0].items.filter((i) => !i.isAd).map((i) => i.id)).toEqual([2]);
  });

  test('标签不再展示，但仍然能被搜索命中', () => {
    const { ctx } = loadPage(COLLECT);
    const withTag = Object.assign(card(1, 'local', '三体解析'), { tags: ['科幻', '三体'] });
    const withoutTag = Object.assign(card(2, 'local', '深度学习入门'), { tags: ['AI'] });
    ctx.setData({ isBound: true, cards: [withTag, withoutTag], keyword: '科幻' });
    ctx.rebuild();

    expect(ctx.data.groups[0].items.filter((i) => !i.isAd).map((i) => i.id)).toEqual([1]);
  });
});
