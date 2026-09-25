const { mapOrigin } = require('../miniprogram/utils/origin.js');

describe('mapOrigin', () => {
  test('没有出处时不渲染（返回 null）', () => {
    expect(mapOrigin(null)).toBeNull();
    expect(mapOrigin(undefined)).toBeNull();
  });

  test('查得到出处时给出完整视图模型', () => {
    const view = mapOrigin({
      account_name: '帅哥录屏',
      account_avatar_url: 'https://cos/avatar.jpg',
      platform: 'douyin',
      platform_label: '抖音',
      author_name: '小山坡',
      author_url: 'https://www.douyin.com/user/MS4w'
    });
    expect(view.accountName).toBe('帅哥录屏');
    expect(view.accountAvatarUrl).toBe('https://cos/avatar.jpg');
    expect(view.platformText).toBe('抖音');
    expect(view.authorText).toBe('@小山坡');
    expect(view.hasAuthor).toBe(true);
    expect(view.authorUrl).toBe('https://www.douyin.com/user/MS4w');
    expect(view.pending).toBe(false);
  });

  test('只知道平台、不知道作者时显示「待补充」', () => {
    const view = mapOrigin({ account_name: '帅哥录屏', platform_label: '抖音' });
    expect(view.platformText).toBe('抖音');
    expect(view.authorText).toBe('待补充');
    expect(view.hasAuthor).toBe(false);
    expect(view.pending).toBe(false);
  });

  test('什么都没有时占位并标记整理中', () => {
    const view = mapOrigin({ account_name: '帅哥录屏' });
    expect(view.platformText).toBe('—');
    expect(view.authorText).toBe('—');
    expect(view.pending).toBe(true);
  });

  test('账号名缺失时兜底为帅哥录屏', () => {
    const view = mapOrigin({ platform_label: '', author_name: '' });
    expect(view.accountName).toBe('帅哥录屏');
    expect(view.accountAvatarUrl).toBe('');
  });

  test('空白字符串按缺失处理', () => {
    const view = mapOrigin({ author_name: '  ', platform_label: '  ' });
    expect(view.pending).toBe(true);
    expect(view.hasAuthor).toBe(false);
  });
});
