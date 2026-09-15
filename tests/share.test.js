const shareablePages = [
  ['home', '../miniprogram/pages/home/home.js'],
  ['collect', '../miniprogram/pages/collect/collect.js'],
  ['mine', '../miniprogram/pages/mine/mine.js'],
  ['about', '../miniprogram/pages/about/about.js'],
  ['help', '../miniprogram/pages/help/help.js']
];

describe('page share menu', () => {
  test.each(shareablePages)('%s supports sharing to chat and timeline', (_, file) => {
    let config;
    global.Page = (value) => {
      config = value;
    };

    require(file);

    expect(typeof config.onShareAppMessage).toBe('function');
    expect(config.onShareAppMessage()).toEqual(expect.objectContaining({
      title: '壁咚咚 · B站视频收藏下载',
      path: '/pages/home/home'
    }));
    expect(typeof config.onShareTimeline).toBe('function');
    expect(config.onShareTimeline()).toEqual(expect.objectContaining({
      title: '壁咚咚 · B站视频收藏下载'
    }));

    delete global.Page;
  });
});
