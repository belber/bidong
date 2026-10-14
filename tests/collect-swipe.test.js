// 收藏夹左右滑动切换视图：和捏合、长按、滚动、编辑态共处同一片手势区。
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const COLLECT = path.join(__dirname, '../miniprogram/pages/collect/collect.js');

function touch(x, y) {
  return [{ clientX: x, clientY: y }];
}

function swipe(ctx, fromX, fromY, toX, toY) {
  ctx.onFeedTouchStart({ touches: touch(fromX, fromY) });
  ctx.onFeedTouchMove({ touches: touch(toX, toY) });
  ctx.onFeedTouchEnd({ touches: [] });
}

function pageView(view) {
  const { ctx, stored } = loadPage(COLLECT);
  ctx.onLoad();
  // 已绑定：否则 rebuild 会打开未绑定引导态，手势会被（正确地）拦掉
  ctx.setData({ isBound: true });
  if (view !== ctx.data.view) {
    ctx.setData({ view });
  }
  return { ctx, stored };
}

describe('收藏夹左右滑动切换视图', () => {
  test('左滑到列表，右滑回网格，并写入本地缓存', () => {
    const { ctx, stored } = pageView('grid');

    swipe(ctx, 300, 400, 180, 404); // 左滑
    expect(ctx.data.view).toBe('list');
    expect(stored.collect_view).toBe('list');

    swipe(ctx, 180, 400, 300, 396); // 右滑
    expect(ctx.data.view).toBe('grid');
    expect(stored.collect_view).toBe('grid');
  });

  test('纵向滚动不切视图（滚动优先）', () => {
    const { ctx, stored } = pageView('grid');

    swipe(ctx, 200, 600, 214, 320);

    expect(ctx.data.view).toBe('grid');
    expect(stored.collect_view).toBeUndefined();
  });

  test('轻微横向抖动不切视图', () => {
    const { ctx } = pageView('grid');

    swipe(ctx, 200, 400, 180, 402);

    expect(ctx.data.view).toBe('grid');
  });

  test('编辑态下不响应滑动（避免选到一半换视图）', () => {
    const { ctx } = pageView('grid');
    ctx.setData({ editing: true });

    swipe(ctx, 300, 400, 180, 400);

    expect(ctx.data.view).toBe('grid');
  });

  test('引导态下不响应滑动（那会儿没有视图切换入口）', () => {
    const { ctx } = pageView('grid');
    ctx.setData({ showRobotGuide: true });

    swipe(ctx, 300, 400, 180, 400);

    expect(ctx.data.view).toBe('grid');
  });

  test('双指捏合时不会被当成滑动', () => {
    const { ctx } = pageView('grid');

    ctx.onFeedTouchStart({ touches: [{ clientX: 300, clientY: 400 }, { clientX: 100, clientY: 400 }] });
    ctx.onFeedTouchMove({ touches: [{ clientX: 250, clientY: 400 }, { clientX: 150, clientY: 400 }] });
    ctx.onFeedTouchEnd({ touches: [] });

    expect(ctx.data.view).toBe('grid');
    expect(ctx.data.cols).toBe(3); // 捏合本身照常生效
  });

  test('滑动结束后那一下点按被吞掉，不会误跳 B站', () => {
    const { ctx } = pageView('grid');
    const nav = [];
    global.wx.navigateTo = (o) => nav.push(o.url);
    ctx.data.cards = [{ id: 'a', bvid: 'BV1' }];

    swipe(ctx, 300, 400, 180, 400);
    ctx.onCardTap({ currentTarget: { dataset: { id: 'a' } } });
    expect(nav).toEqual([]);

    ctx.tapGuardUntil = Date.now() - 1; // 保护窗口过去后恢复正常点按
    ctx.onCardTap({ currentTarget: { dataset: { id: 'a' } } });
    expect(nav).toEqual(['/pages/result/result?bvid=BV1']);
  });
});
