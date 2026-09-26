const path = require('path');
const { loadPage: loadPageHelper } = require('./helpers/page.js');

// 后端返回的 origin 用的是 snake_case（和 cover_url / up_name 一致），
// 这个测试直接用真实响应体喂给页面的 applyResult，防止字段名对不上还一路绿灯。
const REAL_RESPONSE = {
  id: 6,
  bvid: 'BV1Nse466EsX',
  title: '【小视频】167-国贸街拍',
  up_name: '帅哥录屏',
  partition: '旅游出行',
  duration: 106,
  pubdate: 1789796701,
  cover_url: 'http://192.168.28.173:8000/media/covers/BV1Nse466EsX.jpg',
  desc: 'YouTube 街拍 #国贸 #街拍 #luke | 原UP：李不然',
  source_url: 'https://www.bilibili.com/video/BV1Nse466EsX',
  source: 'local',
  tags: ['luke', '国贸', '帅哥', '街拍'],
  collected_at: 1789812310,
  month: '2026-09',
  subtitles: [],
  stats: { like: 46, reply: 3, favorite: 82, coin: 0 },
  danmaku_count: 0,
  media: { watermarked: true, clean: false, audio: true },
  features: { comment: true, danmaku: true },
  origin: {
    account_name: '帅哥录屏',
    account_avatar_url: 'http://192.168.28.173:8000/media/covers/avatar.jpg',
    platform: 'douyin',
    platform_label: '抖音',
    author_name: '李不然',
    author_handle: 'luke0123',
    author_url: 'https://www.douyin.com/user/MS4wLjABAAAAu7JAjWKskIY'
  }
};

const PAGE = path.join(__dirname, '../miniprogram/pages/result/result.js');

function loadPage() {
  const harness = loadPageHelper(PAGE);
  return { page: harness.ctx, toasts: harness.toasts };
}

// 共用脚手架已经装好了 setData 与副作用桩，这里保留旧写法当别名
function mount(page) {
  return page;
}

describe('解析结果页 applyResult', () => {
  test('真实响应体里能读出出处区块的展示文案', () => {
    const { page } = loadPage();
    const ctx = mount(page);
    ctx.applyResult(REAL_RESPONSE);

    expect(ctx.data.title).toBe('【小视频】167-国贸街拍');
    expect(ctx.data.origin).not.toBeNull();
    expect(ctx.data.origin.accountName).toBe('帅哥录屏');
    expect(ctx.data.origin.accountAvatarUrl).toBe(
      'http://192.168.28.173:8000/media/covers/avatar.jpg'
    );
    expect(ctx.data.origin.platformText).toBe('抖音');
    expect(ctx.data.origin.authorText).toBe('@李不然');
    expect(ctx.data.origin.hasAuthor).toBe(true);
    // 复制的是抖音号，不是昵称
    expect(ctx.data.origin.copyText).toBe('luke0123');
    expect(ctx.data.origin.copyKind).toBe('handle');
    expect(ctx.data.origin.pending).toBe(false);
  });

  test('别的 UP 主（origin 为 null）不渲染该区块', () => {
    const { page } = loadPage();
    const ctx = mount(page);
    ctx.applyResult(Object.assign({}, REAL_RESPONSE, { origin: null }));
    expect(ctx.data.origin).toBeNull();
  });

  test('后端只回了平台、没回作者时显示待补充', () => {
    const { page } = loadPage();
    const ctx = mount(page);
    ctx.applyResult(Object.assign({}, REAL_RESPONSE, {
      origin: { account_name: '帅哥录屏', platform_label: '抖音' }
    }));
    expect(ctx.data.origin.platformText).toBe('抖音');
    expect(ctx.data.origin.authorText).toBe('待补充');
  });

  test('没有解析数据时给出提示', () => {
    const { page, toasts } = loadPage();
    const ctx = mount(page);
    ctx.applyResult(null);
    expect(toasts).toContain('暂无解析数据');
  });
});
