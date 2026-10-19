const {
  classifyError,
  domainFromUrl,
  downloadMedia,
  downloadUrlErrorType,
  configuredCandidates,
  looksLikeWebPageOrJson
} = require('../miniprogram/utils/mediaDownload.js');

const MP4_HEAD = Buffer.from([0x00, 0x00, 0x00, 0x20, 0x66, 0x74, 0x79, 0x70]);
const REDIRECT_PAGE = Buffer.from('<a href="https://n98-v-ncdnon.douyinvod.com/x">302</a>');

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

describe('downloadUrlErrorType', () => {
  test('识别后端数据库未登记域名', () => {
    expect(downloadUrlErrorType({
      statusCode: 502,
      data: { error_type: 'domain_not_registered' }
    })).toBe('domain_not_registered');
  });

  test('普通后端错误归为 http_error', () => {
    expect(downloadUrlErrorType({ statusCode: 502, data: {} })).toBe('http_error');
  });

  test('未知错误归为 unknown', () => {
    expect(downloadUrlErrorType({})).toBe('unknown');
  });
});

describe('configuredCandidates', () => {
  test('只返回已配置候选', () => {
    const candidates = [
      { url: 'https://a.example.com/a.mp4', configured: false },
      { url: 'https://b.example.com/b.mp4', configured: true },
      { url: 'https://c.example.com/c.mp4', configured: true }
    ];
    expect(configuredCandidates(candidates).map((c) => c.url)).toEqual([
      'https://b.example.com/b.mp4',
      'https://c.example.com/c.mp4'
    ]);
  });

  test('没有候选时返回空数组', () => {
    expect(configuredCandidates([])).toEqual([]);
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

describe('looksLikeWebPageOrJson', () => {
  test('HTML 跳转页判定为非媒体', () => {
    expect(looksLikeWebPageOrJson('<a href="https://n98-v-ncdnon.douyinvod.com/x">302</a>'))
      .toBe(true);
    expect(looksLikeWebPageOrJson('\n  <!DOCTYPE html>')).toBe(true);
  });

  test('JSON 错误体判定为非媒体', () => {
    expect(looksLikeWebPageOrJson('{"status_code":8,"status_msg":"expired"}')).toBe(true);
    expect(looksLikeWebPageOrJson('[{"a":1}]')).toBe(true);
  });

  test('空内容与正常文件头都放行', () => {
    expect(looksLikeWebPageOrJson('')).toBe(false);
    expect(looksLikeWebPageOrJson('\u0000\u0000\u0000 ftypisom')).toBe(false);
  });
});

// 抖音的 `/aweme/v1/play/` 候选会回 200 + 几百字节的 HTML 跳转页。
// 只按状态码判成功就会把跳转页当视频存进相册（下载成功但打不开）。
function wxWithFiles(files) {
  return {
    downloadFile: jest.fn((opts) => {
      const tempFilePath = opts.url.includes('amemv') ? '/tmp/redirect' : '/tmp/video.mp4';
      opts.success({ statusCode: 200, tempFilePath });
      return { abort: jest.fn(), onProgressUpdate() {} };
    }),
    getFileSystemManager: () => ({
      statSync: (filePath) => ({ size: files[filePath] ? files[filePath].length : 0 }),
      readFileSync: (filePath) => files[filePath]
    })
  };
}

describe('downloadMedia 下载内容校验', () => {
  const candidates = [
    { url: 'https://api-play-hl.amemv.com/aweme/v1/play/?video_id=1', host: 'api-play-hl.amemv.com' },
    { url: 'https://v81-cold.douyinvod.com/x.mp4', host: 'v81-cold.douyinvod.com' }
  ];

  afterEach(() => {
    delete global.wx;
  });

  test('候选回了 200 但内容是跳转页时不算成功，继续试下一个', async () => {
    global.wx = wxWithFiles({ '/tmp/redirect': REDIRECT_PAGE, '/tmp/video.mp4': MP4_HEAD });

    const result = await downloadMedia(candidates);
    expect(result.tempFilePath).toBe('/tmp/video.mp4');
    expect(result.candidateIndex).toBe(1);
    expect(global.wx.downloadFile).toHaveBeenCalledTimes(2);
  });

  test('跳转页按 not_media 上报，便于管理端区分失败原因', async () => {
    const events = [];
    global.wx = wxWithFiles({ '/tmp/redirect': REDIRECT_PAGE, '/tmp/video.mp4': MP4_HEAD });

    await downloadMedia(candidates, {
      report(evt) {
        events.push(evt);
      }
    });

    const failEvent = events.find((e) => e.status === 'fail');
    expect(failEvent.error_type).toBe('not_media');
    expect(failEvent.host).toBe('api-play-hl.amemv.com');
  });

  test('拿不到文件系统接口时放行，不误杀正常下载', async () => {
    const urls = [candidates[1]];
    global.wx = {
      downloadFile: jest.fn((opts) => {
        opts.success({ statusCode: 200, tempFilePath: '/tmp/video.mp4' });
      })
    };

    const result = await downloadMedia(urls);
    expect(result.tempFilePath).toBe('/tmp/video.mp4');
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

  test('下载过程触发 onProgress', async () => {
    const progress = [];
    global.wx = {
      downloadFile: jest.fn((opts) => {
        const task = {
          onProgressUpdate(cb) {
            cb({ progress: 42, totalBytesWritten: 42, totalBytesExpectedToWrite: 100 });
          }
        };
        opts.success({ statusCode: 200, tempFilePath: '/tmp/a.mp4' });
        return task;
      })
    };

    await downloadMedia(candidates, {
      onProgress(res) {
        progress.push(res.progress);
      }
    });

    expect(progress).toEqual([0, 42]);
    expect(global.wx.downloadFile).toHaveBeenCalledTimes(1);
  });
});

describe('downloadMediaParallel', () => {
  const { downloadMediaParallel } = require('../miniprogram/utils/mediaDownload.js');

  afterEach(() => {
    delete global.wx;
  });

  test('下载时把默认 60 秒超时拉长到 30 分钟', async () => {
    const candidates = [
      { url: 'https://a.example.com/a.mp4', host: 'a.example.com' }
    ];
    let captured;
    global.wx = {
      downloadFile: jest.fn((opts) => {
        captured = opts;
        opts.success({ statusCode: 200, tempFilePath: '/tmp/a.mp4' });
        return { abort: jest.fn(), onProgressUpdate() {} };
      })
    };

    await downloadMediaParallel(candidates);
    expect(captured.timeout).toBe(1800000);
  });

  test('并发发起所有候选，第一个成功即返回', async () => {
    const candidates = [
      { url: 'https://a.example.com/a.mp4', host: 'a.example.com', configured: true },
      { url: 'https://b.example.com/b.mp4', host: 'b.example.com', configured: true }
    ];
    const called = [];
    global.wx = {
      downloadFile: jest.fn((opts) => {
        called.push(opts.url);
        const task = { abort: jest.fn(), onProgressUpdate() {} };
        if (opts.url.includes('b.example.com')) {
          opts.success({ statusCode: 200, tempFilePath: '/tmp/b.mp4' });
        }
        return task;
      })
    };

    const result = await downloadMediaParallel(candidates);
    expect(result.tempFilePath).toBe('/tmp/b.mp4');
    expect(result.candidateIndex).toBe(1);
    expect(called).toEqual(['https://a.example.com/a.mp4', 'https://b.example.com/b.mp4']);
  });

  test('首个成功后会取消其余下载任务', async () => {
    const candidates = [
      { url: 'https://a.example.com/a.mp4', host: 'a.example.com' },
      { url: 'https://b.example.com/b.mp4', host: 'b.example.com' }
    ];
    const tasks = [];
    global.wx = {
      downloadFile: jest.fn((opts) => {
        const task = { abort: jest.fn(), onProgressUpdate() {} };
        tasks.push(task);
        if (opts.url.includes('b.example.com')) {
          opts.success({ statusCode: 200, tempFilePath: '/tmp/b.mp4' });
        }
        return task;
      })
    };

    await downloadMediaParallel(candidates);
    expect(tasks[0].abort).toHaveBeenCalled();
  });

  test('全部失败时 reject 并标记 allFailed', async () => {
    const candidates = [
      { url: 'https://a.example.com/a.mp4', host: 'a.example.com' },
      { url: 'https://b.example.com/b.mp4', host: 'b.example.com' }
    ];
    global.wx = {
      downloadFile: jest.fn((opts) => {
        const task = { abort: jest.fn(), onProgressUpdate() {} };
        opts.fail({ errMsg: 'downloadFile:fail network error' });
        return task;
      })
    };

    await expect(downloadMediaParallel(candidates)).rejects.toEqual(
      expect.objectContaining({ allFailed: true })
    );
  });

  test('并发候选里拿到跳转页的那个不算成功', async () => {
    const candidates = [
      { url: 'https://api-play-hl.amemv.com/aweme/v1/play/?video_id=1', host: 'api-play-hl.amemv.com' },
      { url: 'https://v81-cold.douyinvod.com/x.mp4', host: 'v81-cold.douyinvod.com' }
    ];
    global.wx = wxWithFiles({ '/tmp/redirect': REDIRECT_PAGE, '/tmp/video.mp4': MP4_HEAD });

    const result = await downloadMediaParallel(candidates);
    expect(result.tempFilePath).toBe('/tmp/video.mp4');
    expect(result.candidateIndex).toBe(1);
  });

  test('并发候选全是跳转页时整体失败', async () => {
    const candidates = [
      { url: 'https://api-play-hl.amemv.com/aweme/v1/play/?video_id=1', host: 'api-play-hl.amemv.com' },
      { url: 'https://api-hl.amemv.com/aweme/v1/play/?video_id=1', host: 'api-hl.amemv.com' }
    ];
    global.wx = wxWithFiles({ '/tmp/redirect': REDIRECT_PAGE });

    await expect(downloadMediaParallel(candidates)).rejects.toEqual(
      expect.objectContaining({ allFailed: true })
    );
  });
});
