const {
  classifyError,
  domainFromUrl,
  downloadMedia
} = require('../miniprogram/utils/mediaDownload.js');

describe('classifyError', () => {
  test('识别微信合法域名未配置', () => {
    expect(classifyError(null, { errMsg: 'downloadFile:fail url not in domain list' }))
      .toBe('domain_not_configured');
  });

  test('识别链接过期', () => {
    expect(classifyError(403, {})).toBe('expired');
  });

  test('识别 HTTP 错误', () => {
    expect(classifyError(500, {})).toBe('http_error');
  });

  test('识别普通微信错误', () => {
    expect(classifyError(null, { errMsg: 'downloadFile:fail network error' }))
      .toBe('wx_error');
  });
});

describe('domainFromUrl', () => {
  test('提取域名', () => {
    expect(domainFromUrl('https://upos-sz-mirrorcoso1.bilivideo.com/a.mp4?x=1'))
      .toBe('upos-sz-mirrorcoso1.bilivideo.com');
  });

  test('空链接返回空字符串', () => {
    expect(domainFromUrl('')).toBe('');
  });
});

describe('downloadMedia', () => {
  const candidates = [
    { url: 'https://a.example.com/a.mp4', host: 'a.example.com' },
    { url: 'https://b.example.com/b.mp4', host: 'b.example.com' }
  ];

  afterEach(() => {
    delete global.wx;
  });

  test('第一个候选成功', async () => {
    global.wx = {
      downloadFile: jest.fn((opts) => {
        opts.success({ statusCode: 200, tempFilePath: '/tmp/a.mp4' });
      })
    };

    const result = await downloadMedia(candidates);
    expect(result.tempFilePath).toBe('/tmp/a.mp4');
    expect(result.candidateIndex).toBe(0);
    expect(global.wx.downloadFile).toHaveBeenCalledTimes(1);
  });

  test('第一个失败后尝试第二个', async () => {
    global.wx = {
      downloadFile: jest.fn((opts) => {
        if (opts.url.includes('a.example.com')) {
          opts.success({ statusCode: 404, tempFilePath: '' });
        } else {
          opts.success({ statusCode: 200, tempFilePath: '/tmp/b.mp4' });
        }
      })
    };

    const result = await downloadMedia(candidates);
    expect(result.candidateIndex).toBe(1);
    expect(global.wx.downloadFile).toHaveBeenCalledTimes(2);
  });

  test('全部失败时 reject', async () => {
    global.wx = {
      downloadFile: jest.fn((opts) => {
        opts.fail({ errMsg: 'downloadFile:fail url not in domain list' });
      })
    };

    await expect(downloadMedia(candidates)).rejects.toEqual(
      expect.objectContaining({ allFailed: true })
    );
    expect(global.wx.downloadFile).toHaveBeenCalledTimes(2);
  });
});
