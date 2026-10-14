// 收藏夹列表/网格双视图：默认网格、切换写入本地缓存、列数靠捏合调整（无按钮）。
const path = require('path');
const { loadPage } = require('./helpers/page.js');

const COLLECT = path.join(__dirname, '../miniprogram/pages/collect/collect.js');
const HINT = '双指捏合可调整列数';

function tap(dataset) {
  return { currentTarget: { dataset } };
}

// 双指水平分开 distance 像素的 touch 事件载荷
function pair(distance) {
  const half = distance / 2;
  return [{ clientX: 200 - half, clientY: 300 }, { clientX: 200 + half, clientY: 300 }];
}

function pinchStart(ctx, distance) {
  ctx.onFeedTouchStart({ touches: pair(distance) });
}

function pinchMove(ctx, distance) {
  ctx.onFeedTouchMove({ touches: pair(distance) });
}

function pinchEnd(ctx) {
  ctx.onFeedTouchEnd({ touches: [] });
}

describe('收藏夹视图偏好', () => {
  test('没有缓存时默认网格 + 2 列', () => {
    const { ctx } = loadPage(COLLECT);
    ctx.onLoad();
    expect(ctx.data.view).toBe('grid');
    expect(ctx.data.cols).toBe(2);
  });

  test('已有缓存时按缓存渲染', () => {
    const { ctx, stored } = loadPage(COLLECT);
    stored.collect_view = 'list';
    stored.collect_cols = '3';
    ctx.onLoad();
    expect(ctx.data.view).toBe('list');
    expect(ctx.data.cols).toBe(3);
  });

  test('切到列表视图并写入本地缓存', () => {
    const { ctx, stored } = loadPage(COLLECT);
    ctx.onLoad();
    ctx.onViewTap(tap({ view: 'list' }));
    expect(ctx.data.view).toBe('list');
    expect(stored.collect_view).toBe('list');
  });

  test('视图与列数互不覆盖：切列表后列数偏好仍在缓存里', () => {
    const { ctx, stored } = loadPage(COLLECT);
    ctx.onLoad();
    pinchStart(ctx, 200);
    pinchMove(ctx, 150);
    pinchEnd(ctx);
    ctx.onViewTap(tap({ view: 'list' }));
    expect(stored.collect_view).toBe('list');
    expect(stored.collect_cols).toBe(3);
  });
});

describe('捏合调整列数', () => {
  test('捏小实时加一列，抬手指才写缓存', () => {
    const { ctx, stored } = loadPage(COLLECT);
    ctx.onLoad();
    pinchStart(ctx, 200);
    pinchMove(ctx, 150); // 0.75 倍
    expect(ctx.data.cols).toBe(3);
    expect(stored.collect_cols).toBeUndefined(); // 手势没结束就不落缓存
    pinchEnd(ctx);
    expect(stored.collect_cols).toBe(3);
  });

  test('持续捏小能连跳到 4 列并封顶', () => {
    const { ctx, stored } = loadPage(COLLECT);
    ctx.onLoad();
    pinchStart(ctx, 200);
    pinchMove(ctx, 150);
    pinchMove(ctx, 120);
    expect(ctx.data.cols).toBe(4);
    pinchMove(ctx, 60);
    expect(ctx.data.cols).toBe(4);
    pinchEnd(ctx);
    expect(stored.collect_cols).toBe(4);
  });

  test('反向捏大能减回列数', () => {
    const { ctx, stored } = loadPage(COLLECT);
    stored.collect_cols = 4;
    ctx.onLoad();
    pinchStart(ctx, 100);
    pinchMove(ctx, 150);
    expect(ctx.data.cols).toBe(3);
    pinchEnd(ctx);
    expect(stored.collect_cols).toBe(3);
  });

  test('只在阈值内轻微移动不改列数', () => {
    const { ctx } = loadPage(COLLECT);
    ctx.onLoad();
    pinchStart(ctx, 200);
    pinchMove(ctx, 190);
    expect(ctx.data.cols).toBe(2);
  });

  test('列表视图下不响应捏合', () => {
    const { ctx, stored } = loadPage(COLLECT);
    stored.collect_view = 'list';
    ctx.onLoad();
    pinchStart(ctx, 200);
    pinchMove(ctx, 100);
    expect(ctx.data.cols).toBe(2);
    pinchEnd(ctx);
    expect(stored.collect_cols).toBeUndefined();
  });

  test('编辑态下不响应捏合（避免选到一半整屏重排）', () => {
    const { ctx } = loadPage(COLLECT);
    ctx.onLoad();
    ctx.setData({ editing: true });
    pinchStart(ctx, 200);
    pinchMove(ctx, 100);
    expect(ctx.data.cols).toBe(2);
  });

  test('单指滑动不算捏合', () => {
    const { ctx } = loadPage(COLLECT);
    ctx.onLoad();
    ctx.onFeedTouchStart({ touches: [{ clientX: 100, clientY: 300 }] });
    ctx.onFeedTouchMove({ touches: [{ clientX: 200, clientY: 300 }] });
    expect(ctx.data.cols).toBe(2);
  });

  test('捏合过程中的误触不跳转 B站，抬手指后短暂仍吞掉一次点按', () => {
    const { ctx } = loadPage(COLLECT);
    const nav = [];
    global.wx.navigateTo = (o) => nav.push(o.url);
    ctx.onLoad();
    ctx.data.cards = [{ id: 'a', bvid: 'BV1' }];

    pinchStart(ctx, 200);
    pinchMove(ctx, 150);
    ctx.onCardTap(tap({ id: 'a' })); // 双指落下时系统仍可能补一个 tap
    expect(nav).toEqual([]);
    pinchEnd(ctx);
    ctx.onCardTap(tap({ id: 'a' }));
    expect(nav).toEqual([]); // 收尾的那一下也吞掉

    ctx.tapGuardUntil = Date.now() - 1; // 保护窗口过去后恢复正常点按
    ctx.onCardTap(tap({ id: 'a' }));
    expect(nav).toEqual(['/pages/result/result?bvid=BV1']);
  });
});

describe('捏合提示', () => {
  test('网格视图首次进入提示一次，之后再进不提示', () => {
    const { ctx, toasts } = loadPage(COLLECT);
    ctx.onLoad();
    expect(toasts.filter((t) => t === HINT).length).toBe(1);
    ctx.onLoad();
    expect(toasts.filter((t) => t === HINT).length).toBe(1);
  });

  test('默认列表视图不提示（对着列表页讲捏合没意义）', () => {
    const { ctx, toasts, stored } = loadPage(COLLECT);
    stored.collect_view = 'list';
    ctx.onLoad();
    expect(toasts).not.toContain(HINT);
  });
});
