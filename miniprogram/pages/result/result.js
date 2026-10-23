const api = require('../../utils/api.js');
const { formatDuration, formatDateTime } = require('../../utils/format.js');
const { mapOrigin } = require('../../utils/origin.js');
const { downloadMediaParallel, downloadUrlErrorType, configuredCandidates, classifyError } = require('../../utils/mediaDownload.js');
const {
  initialExports,
  beginExport,
  updateExportProgress,
  completeExport,
  failExport,
  markExportSaved,
  exportLabel
} = require('../../utils/exportState.js');

function toast(title) {
  wx.showToast({ title: title, icon: 'none' });
}

// 出处头像和封面同样有两种形态：本地后端给相对路径（用 apiBase 拼），
// COS（生产）给绝对地址，原样用。mapOrigin 保持纯函数，这里再补一次地址。
function resolveOriginAvatar(origin) {
  if (!origin || !origin.accountAvatarUrl) {
    return origin;
  }
  origin.accountAvatarUrl = api.resolveMediaUrl(origin.accountAvatarUrl);
  return origin;
}

// 一次下载的标识：同一次下载的每个阶段带同一个 id，后端据此把事件聚合回"一次下载"
function newSessionId() {
  return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
}

function sanitizeName(name) {
  const cleaned = (name || '').replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, ' ').trim();
  return (cleaned || 'bilibili').slice(0, 60);
}

function mediaFilename(title, bvid, kind) {
  const suffix = kind === 'audio' ? '.m4a' : '.mp4';
  return sanitizeName(title || bvid) + suffix;
}

function formatSize(bytes) {
  if (!bytes || bytes <= 0) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB';
 }

function formatSpeed(bytesPerSecond) {
  if (!bytesPerSecond || bytesPerSecond <= 0) return '';
  if (bytesPerSecond < 1024) return bytesPerSecond.toFixed(0) + ' B/s';
  if (bytesPerSecond < 1024 * 1024) return (bytesPerSecond / 1024).toFixed(1) + ' KB/s';
  return (bytesPerSecond / 1024 / 1024).toFixed(1) + ' MB/s';
}

function textFilename(title, bvid, suffix) {
  return sanitizeName(title || bvid) + suffix;
}

function copyToNamed(tempFilePath, filename) {
  return new Promise((resolve, reject) => {
    const dest = wx.env.USER_DATA_PATH + '/' + filename;
    const fs = wx.getFileSystemManager();
    try { fs.unlinkSync(dest); } catch (e) { /* 保留：目录不存在或文件不存在 */ }
    fs.copyFile({
      srcPath: tempFilePath,
      destPath: dest,
      success: () => resolve(dest),
      fail: reject
    });
  });
}

function saveToAlbum(saveFn, filePath) {
  saveFn({
    filePath,
    success() { toast('已保存到相册'); },
    fail() {
      wx.showModal({
        title: '保存失败',
        content: '需要在设置中允许保存到相册',
        confirmText: '去设置',
        success(res) {
          if (res.confirm) { wx.openSetting(); }
        }
      });
    }
  });
}

function ensureAlbumPermission() {
  return new Promise((resolve, reject) => {
    if (!wx.getSetting) {
      resolve();
      return;
    }
    wx.getSetting({
      success(res) {
        const setting = res.authSetting || {};
        const state = setting['scope.writePhotosAlbum'];
        if (state === true) {
          resolve();
          return;
        }
        if (state === false) {
          reject({ errMsg: 'auth deny scope.writePhotosAlbum' });
          return;
        }
        wx.authorize({
          scope: 'scope.writePhotosAlbum',
          success: resolve,
          fail: reject
        });
      },
      fail: reject
    });
  });
}

function showAlbumPermissionGuide() {
  wx.showModal({
    title: '需要相册权限',
    content: '请在设置中允许“保存到相册”，然后重试。',
    confirmText: '去设置',
    success(res) {
      if (res.confirm && wx.openSetting) {
        wx.openSetting();
      }
    }
  });
}

function writeImageFile(filePath, data) {
  return new Promise((resolve, reject) => {
    wx.getFileSystemManager().writeFile({
      filePath,
      data,
      success: resolve,
      fail: reject
    });
  });
}

function saveImageToAlbum(filePath) {
  return new Promise((resolve, reject) => {
    wx.saveImageToPhotosAlbum({
      filePath,
      success: resolve,
      fail: reject
    });
  });
}

function shareLocalFile(localPath, filename) {
  if (!wx.shareFileMessage) {
    toast('当前微信版本不支持文件分享');
    return;
  }
  wx.shareFileMessage({
    filePath: localPath,
    fileName: filename,
    fail(err) { toast((err && err.errMsg) || '分享失败'); }
  });
}

function saveVideoPromise(filePath) {
  return new Promise((resolve, reject) => {
    wx.saveVideoToPhotosAlbum({
      filePath,
      success: () => resolve(),
      fail: reject
    });
  });
}

function shareFilePromise(filePath, filename) {
  return new Promise((resolve, reject) => {
    if (!wx.shareFileMessage) {
      reject(new Error('当前微信版本不支持文件分享'));
      return;
    }
    wx.shareFileMessage({
      filePath,
      fileName: filename,
      success: () => resolve(),
      fail: reject
    });
  });
}

Page({
  data: {
    resultAdUnitId: require('../../utils/ads.js').AD_UNIT_IDS.resultBanner,
    resultAdError: false,
    cardId: 0,
    bvid: '',
    sourceUrl: '',
    title: '',
    upName: '',
    partition: '',
    pubText: '',
    tags: [],
    tagsText: '',
    desc: '',
    stats: { like: 0, reply: 0, favorite: 0, coin: 0 },
    coverUrl: '',
    origin: null,
    media: { watermarked: false, clean: false, audio: false },
    features: { comment: true, danmaku: true },
    shareEnabled: true,
    subtitles: [],
    subPreview: [],
    showAllSub: false,
    danmakuCount: 0,
    previewing: false,
    exports: initialExports(),
    mediaSize: {},
    downloading: false,
    downloadProgress: 0,
    downloadSizeText: '',
    fallbackVisible: false,
    fallbackUrl: '',
    activeKind: '',
    activeQn: null,
    publicView: false,
    audioUnavailable: false,
    imagePercent: 0,
    imageStatus: ''
  },

  onLoad(options) {
    this.loadUiConfig();
    // 老链接/朋友圈只带 id= 时也按抖音处理，避免拼成 bilibili.com/video/<aweme_id>
    const explicitPlatform = options && options.platform;
    const platform =
      explicitPlatform === 'douyin' || (!explicitPlatform && options && options.id)
        ? 'douyin'
        : 'bilibili';
    // B站 走 ?bvid=，抖音走 ?platform=douyin&id=<aweme_id>；旧的 B站 分享链接继续有效
    const videoId = (options && (options.bvid || options.id)) || '';
    const pending =
      getApp().globalData.pendingResult || wx.getStorageSync('pending_result');
    if (videoId) {
      // URL 自包含：先用刚解析出来的结果秒开，再按 id 拉一次最新（静默，不闪 loading）
      const fresh =
        pending && pending.bvid === videoId && (pending.platform || 'bilibili') === platform;
      if (fresh) {
        this.applyResult(pending);
      }
      this.loadByPlatform(platform, videoId, { silent: fresh });
      return;
    }
    this.applyResult(pending);
  },

  loadUiConfig() {
    api
      .getPublicConfig()
      .then((cfg) => {
        this.setData({ shareEnabled: cfg.share !== false });
      })
      .catch(() => {});
  },

  sourceOf(platform, videoId) {
    return platform === 'douyin'
      ? 'https://www.douyin.com/video/' + videoId
      : 'https://www.bilibili.com/video/' + videoId;
  },

  loadByBvid(bvid, opts) {
    return this.loadByPlatform('bilibili', bvid, opts);
  },

  loadByPlatform(platform, videoId, opts) {
    const silent = !!(opts && opts.silent);
    if (!silent) {
      wx.showLoading({ title: '加载中' });
    }
    api.parse(this.sourceOf(platform, videoId))
      .then((card) => {
        wx.hideLoading();
        getApp().globalData.pendingResult = card;
        wx.setStorageSync('pending_result', card);
        this.applyResult(card);
      })
      .catch((err) => {
        wx.hideLoading();
        // 没有登录态（未登录访客、微信搜索爬虫）或登录失效时，退回公开信息渲染：
        // 页面必须"打开就有内容"，否则分享出去/被爬虫抓到的都是空页面
        const authIssue = !err || !err.statusCode || err.statusCode === 401;
        if (!authIssue) {
          if (!silent) toast(err.message || '加载失败');
          return;
        }
        api.getPublicCard(videoId, platform)
          .then((card) => {
            this.applyResult(card, { publicView: true });
          })
          .catch(() => {
            if (!silent) toast(err.message || '加载失败');
          });
      });
  },

  applyResult(r, opts) {
    if (!r) {
      toast('暂无解析数据');
      return;
    }
    const publicView = !!(opts && opts.publicView);
    const subtitles = (r.subtitles || []).map((s) => ({
      t: s.t,
      text: s.text,
      timeText: formatDuration(s.t)
    }));
    const tags = Array.isArray(r.tags) ? r.tags : [];
    const platform = r.platform === 'douyin' ? 'douyin' : 'bilibili';
    const media = r.media || { watermarked: false, clean: false, audio: false, images: 0 };
    // 换了一张卡片就丢掉上一张的图片数据缓存
    if (this.data.cardId !== r.id) {
      this._imagesCache = null;
    }
    this.setData({
      cardId: r.id,
      platform,
      isDouyin: platform === 'douyin',
      bvid: r.bvid,
      sourceUrl: r.source_url,
      title: r.title,
      upName: r.up_name,
      partition: r.partition || '',
      // 抖音没有分区，基本信息里这一行换成抖音号（后端 author_id）
      douyinId: r.author_id || '',
      pubText: formatDateTime(r.pubdate),
      tags,
      tagsText: tags.join(' '),
      desc: r.desc,
      stats: r.stats || { like: 0, reply: 0, favorite: 0, coin: 0, share: 0 },
      coverUrl: api.resolveMediaUrl(r.cover_url),
      origin: resolveOriginAvatar(mapOrigin(r.origin)),
      media,
      imageCount: media.images || 0,
      isNote: media.note === true,
      features: r.features || { comment: true, danmaku: true },
      danmakuCount: r.danmaku_count || 0,
      subtitles,
      subPreview: subtitles.slice(0, 5),
      exports: initialExports(),
      savingImages: false,
      imagePercent: 0,
      imageProgress: '',
      imageStatus: '',
      publicView
    });
    // 导航标题跟着视频走：搜索结果里的标题相关性靠它
    // 标题按平台带对应的搜索词：内容页的相关性比品牌后缀更值钱
    const titleSuffix = platform === 'douyin' ? '抖音视频下载' : 'B站视频下载';
    wx.setNavigationBarTitle({
      title: this.data.title ? this.data.title + ' · ' + titleSuffix : titleSuffix
    });
    this.loadMediaSize(r.id);
  },

  loadMediaSize(cardId) {
    api.mediaSize(cardId).then((sizes) => {
      const labels = {};
      if (sizes.watermarked) labels.watermarked = '约 ' + formatSize(sizes.watermarked);
      if (sizes.clean) labels.clean = '约 ' + formatSize(sizes.clean);
      // 抖音同样报大小：视频用后端 detail 里的 data_size，音频由后端 HEAD 一次 CDN
      if (sizes.video) labels.video = '约 ' + formatSize(sizes.video);
      if (sizes.audio) labels.audio = '约 ' + formatSize(sizes.audio);
      this.setData({ mediaSize: labels });
    }).catch(() => {});
  },

  copy(field) {
    const v = this.data[field];
    if (!v || (Array.isArray(v) && !v.length)) {
      toast('没有可复制的内容');
      return;
    }
    const text = Array.isArray(v) ? v.map((t) => '#' + t).join(' ') : String(v);
    wx.setClipboardData({ data: text, success() { toast('已复制'); } });
  },

  onResultAdError(e) {
    console.warn('[ad] 结果页横幅加载失败', e && e.detail);
    this.setData({ resultAdError: true });
  },

  onCopyTag(e) {
    this.copy(e.currentTarget.dataset.field);
  },

  // 复制原作者昵称：粉丝拿到手机上最顺手的动作是去抖音/微博搜索框粘贴查人，
  // 直接粘主页链接在 App 里查不到
  onCopyAuthorName() {
    const origin = this.data.origin;
    const name = origin && origin.copyText;
    if (!name) {
      toast('没有可复制的账号');
      return;
    }
    const platform = origin.platformText && origin.platformText !== '—' ? origin.platformText : '';
    const what = origin.copyKind === 'handle' ? '账号' : '昵称';
    wx.setClipboardData({
      data: name,
      success() { toast(platform ? '已复制' + what + '，去' + platform + '搜索' : '已复制' + what); }
    });
  },

  onPreviewCover() {
    if (this.data.coverUrl) {
      this.setData({ previewing: true });
    }
  },

  onClosePreview() {
    this.setData({ previewing: false });
  },

  onSaveCover() {
    const url = this.data.coverUrl;
    if (!url) { return; }
    wx.showLoading({ title: '下载中' });
    wx.downloadFile({
      url,
      success(res) {
        wx.hideLoading();
        if (res.statusCode !== 200) { toast('下载失败'); return; }
        saveToAlbum(wx.saveImageToPhotosAlbum, res.tempFilePath);
      },
      fail() { wx.hideLoading(); toast('下载失败'); }
    });
  },

  // ---------------------------------------------------------------------
  // 抖音：直链交给客户端自己去 CDN 拉，服务端不中转
  // ---------------------------------------------------------------------
  fetchDouyinCandidates(kind) {
    return api.downloadUrl(this.data.cardId, kind).then((data) => {
      const all = data.candidates || [];
      return { all: all, configured: configuredCandidates(all) };
    });
  },

  onDownloadDouyin(e) {
    const kind = e.currentTarget.dataset.kind || 'video';
    // 音频走导出状态机（onExportTap → 分享文件），相册存不了 MP3
    if (kind !== 'video') {
      return;
    }
    // activeKind 决定哪一行显示百分比和进度条；B站 的 onDownloadVideo 也这么做
    this.setData({ activeKind: kind });
    this._sessionId = newSessionId();
    this.fetchDouyinCandidates(kind)
      .then((res) => {
        const autoCandidates = configuredCandidates(res.all);
        if (!autoCandidates.length) {
          // 一个候选都没登记进微信白名单，直接给复制链接的办法
          this.reportDownload('resolve', 'fail', {
            kind,
            error_type: 'domain_not_configured',
            error_message: '暂无可用的已配置下载域名'
          });
          this.setData({ activeKind: '' });
          this.openFallback(res.all);
          return;
        }
        this.saveMedia(autoCandidates, kind);
      })
      .catch((err) => {
        const msg = (err && err.message) || '取下载地址失败';
        this.reportDownload('resolve', 'fail', {
          kind,
          error_type: downloadUrlErrorType(err),
          error_message: msg
        });
        this.setData({ activeKind: '' });
        toast(msg);
      });
  },

  // 图文：后端下载图片并返回数据；小程序只走已配置的 request 域名。
  onSaveImages() {
    if (this.data.savingImages) {
      return;
    }
    // 守卫必须在请求前落下：取图要 1~2 秒，这期间按钮仍可点，晚设会重复跑整组下载
    this._sessionId = newSessionId();
    this.setData({
      savingImages: true,
      imageProgress: '',
      imageStatus: '正在准备图片…',
      imagePercent: 0
    });
    this.loadDouyinImages()
      .then((payload) => {
        const list = payload.items || [];
        if (!list.length) {
          this.resetSavingImages();
          const message = '图片下载失败，请稍后重试';
          this.reportDownload('resolve', 'fail', {
            kind: 'image',
            error_type: 'image_data',
            error_message: message
          });
          toast(message);
          return;
        }
        this.setData({ imageStatus: '正在保存 0/' + list.length + ' 张', imagePercent: 0 });
        let done = 0;
        let failed = (payload.failed || []).length;
        let lastError = '';
        const finish = () => {
          this.resetSavingImages();
          this.reportDownload('save', failed ? 'fail' : 'success', {
            kind: 'image',
            error_type: failed ? 'wx_save_image' : '',
            error_message: failed ? (lastError || failed + ' 张保存失败') : '',
            wx_err_msg: lastError
          });
          toast(failed ? '已保存 ' + done + ' 张，' + failed + ' 张失败' : '已保存 ' + done + ' 张图片');
        };
        const next = (i) => {
          if (i >= list.length) {
            finish();
            return;
          }
          const item = list[i];
          this.setData({
            imageStatus: '正在保存 ' + (i + 1) + '/' + list.length + ' 张',
            imagePercent: Math.round((i / list.length) * 100)
          });
          let buffer;
          try {
            buffer = wx.base64ToArrayBuffer(item.base64);
          } catch (err) {
            failed += 1;
            lastError = (err && err.errMsg) || '图片数据解码失败';
            next(i + 1);
            return;
          }
          const filePath = wx.env.USER_DATA_PATH + '/douyin-' + this.data.bvid + '-' +
            Date.now() + '-' + (i + 1) + '.' + (item.ext || 'jpg');
          writeImageFile(filePath, buffer)
            .then(() => saveImageToAlbum(filePath))
            .then(() => {
              done += 1;
              // 让出一次事件循环，先让进度条上屏，再处理下一张
              setTimeout(() => next(i + 1), 0);
            })
            .catch((err) => {
              failed += 1;
              lastError = (err && err.errMsg) || (err && err.message) || '保存失败';
              setTimeout(() => next(i + 1), 0);
            });
        };
        ensureAlbumPermission()
          .then(() => setTimeout(() => next(0), 0))
          .catch((err) => {
            this.resetSavingImages();
            const wxErr = (err && err.errMsg) || 'auth deny scope.writePhotosAlbum';
            this.reportDownload('save', 'fail', {
              kind: 'image',
              error_type: 'album_permission',
              error_message: '未获得相册权限',
              wx_err_msg: wxErr
            });
            showAlbumPermissionGuide();
          });
      })
      .catch((err) => {
        this.resetSavingImages();
        const message = (err && err.message) || '图片下载失败';
        this.reportDownload('resolve', 'fail', {
          kind: 'image',
          error_type: 'image_data',
          error_message: message
        });
        toast(message);
      });
  },

  // 图片数据按卡片缓存：同一组图重复“保存全部”时不再重新拉一遍 2MB+ 的 base64
  loadDouyinImages() {
    const cache = this._imagesCache;
    if (cache && cache.cardId === this.data.cardId) {
      return Promise.resolve(cache.payload);
    }
    return api.douyinImages(this.data.cardId).then((payload) => {
      this._imagesCache = { cardId: this.data.cardId, payload };
      return payload;
    });
  },

  resetSavingImages() {
    this.setData({
      savingImages: false,
      imageProgress: '',
      imageStatus: '',
      imagePercent: 0
    });
  },

  // 抖音没有可以在微信里跳过去的小程序，只能复制作品链接 + 提示去 App
  onOpenDouyin() {
    const url =
      this.data.sourceUrl ||
      'https://www.douyin.com/video/' + this.data.bvid;
    wx.setClipboardData({
      data: url,
      success() {
        wx.showModal({
          title: '去抖音查看',
          content: '作品链接已复制。打开抖音 App，粘贴到搜索框即可看到这条作品。',
          showCancel: false,
          confirmText: '知道了'
        });
      }
    });
  },

  saveMedia(candidates, kind) {
    this.setData({ downloading: true, downloadProgress: 0, downloadSizeText: '' });
    const filename = kind === 'audio'
      ? mediaFilename(this.data.title, this.data.bvid, 'audio')
      : mediaFilename(this.data.title, this.data.bvid, 'video');

    downloadMediaParallel(candidates, {
      header: api.authHeader(),
      report: (evt) => this.reportDownload(evt.stage, evt.status, evt),
      onProgress: (res) => {
        const written = formatSize(res.totalBytesWritten);
        const total = formatSize(res.totalBytesExpectedToWrite);
        this.setData({
          downloadProgress: Math.max(0, Math.min(100, res.progress || 0)),
          downloadSizeText: written && total ? ' ' + written + '/' + total : ''
        });
      }
    }).then((result) => {
      this.setData({ downloading: false });
      return copyToNamed(result.tempFilePath, filename)
        .then((filePath) => {
          return saveVideoPromise(filePath).then(() => {
            this.reportDownload('save', 'success', { host: result.host });
            toast('已保存到相册');
          });
        })
        .catch((err) => {
          return saveVideoPromise(result.tempFilePath).then(() => {
            this.reportDownload('save', 'success', { host: result.host });
            toast('已保存到相册');
          }).catch((saveErr) => {
            this.reportDownload('save', 'fail', {
              host: result.host,
              error_type: 'permission',
              error_message: (saveErr && saveErr.errMsg) || '保存失败'
            });
            this.openFallback(candidates);
          });
        });
    }).catch((err) => {
      this.setData({ downloading: false });
      this.openFallback(candidates);
    });
  },

  onDownloadVideo(e) {
    const kind = e.currentTarget.dataset.kind || 'watermarked';
    this.setData({ activeKind: kind });
    api.mediaOptions(this.data.cardId, kind).then((options) => {
      if (!options.length) {
        toast('无可用清晰度');
        return;
      }
      wx.showActionSheet({
        itemList: options.map((o) => o.label),
        success: (res) => {
          const chosen = options[res.tapIndex];
          this._sessionId = newSessionId();
          this.setData({ activeQn: chosen.qn });
          api.downloadUrl(this.data.cardId, kind, chosen.qn).then((data) => {
            const autoCandidates = configuredCandidates(data.candidates);
            if (!autoCandidates.length) {
              this.reportDownload('resolve', 'fail', {
                error_type: 'domain_not_registered',
                error_message: '暂无已配置的下载域名',
                http_status: null
              });
              this.openFallback(data.candidates);
              return;
            }
            this.reportDownload('resolve', 'success', {});
            this.saveMedia(autoCandidates, kind);
          }).catch((err) => {
            const errorType = downloadUrlErrorType(err);
            this.reportDownload('resolve', 'fail', {
              error_type: errorType,
              error_message: (err && err.message) || '获取下载地址失败',
              http_status: (err && err.statusCode) || null
            });
            toast((err && err.message) || '获取下载地址失败');
          });
        }
      });
    }).catch(() => {
      this.reportDownload('resolve', 'fail', { error_type: 'unknown', error_message: '获取清晰度失败' });
      toast('获取清晰度失败');
    });
  },

  onExportTap(e) {
    const kind = e.currentTarget.dataset.kind;
    const item = this.data.exports[kind];
    if (!item) return;
    if (item.state === 'downloading') return;
    if (item.state === 'ready' || item.state === 'saved') {
      this.shareExport(kind);
      return;
    }
    this.startExport(kind);
  },

  exportRequest(kind) {
    if (kind === 'subtitle') return api.exportFile(this.data.cardId, 'srt');
    if (kind === 'danmaku') return api.danmaku(this.data.cardId);
    if (kind === 'comment') return api.comments(this.data.cardId);
    if (this.data.isDouyin) {
      // 抖音音频是 CDN 直链，服务端不中转，所以不走 api.download 那条后端代理；
      // 拿地址这一步失败要抛出，交给 startExport 统一落成 failed 状态。
      return api.downloadUrl(this.data.cardId, 'audio').then((data) => {
        const list = data.candidates || [];
        const ready = configuredCandidates(list);
        if (!ready.length) {
          // 一个候选都没登记进微信白名单：直链给了也下不动，走兜底让用户复制链接。
          const err = new Error('暂无可用的已配置下载域名');
          err.code = 'domain_not_configured';
          throw err;
        }
        return { url: ready[0].url, header: {} };
      });
    }
    return api.download(this.data.cardId, 'audio');
  },

  exportName(kind) {
    if (kind === 'subtitle') return textFilename(this.data.title, this.data.bvid, '.srt');
    if (kind === 'danmaku') return textFilename(this.data.title, this.data.bvid, '_弹幕.txt');
    if (kind === 'comment') return textFilename(this.data.title, this.data.bvid, '_评论.txt');
    return mediaFilename(this.data.title, this.data.bvid, 'audio');
  },

  startExport(kind) {
    const filename = this.exportName(kind);
    this._sessionId = newSessionId();
    this._downloadSpeed = this._downloadSpeed || {};
    this._downloadSpeed[kind] = null;
    this.setData({ exports: beginExport(this.data.exports, kind) });
    this.exportRequest(kind).then(({ url, header }) => {
      const task = wx.downloadFile({
        url,
        header,
        timeout: 600000,
        success: (res) => {
          if (res.statusCode !== 200) {
            this.setData({ exports: failExport(this.data.exports, kind) });
            this.reportDownload('download', 'fail', {
              kind,
              error_type: 'http_error',
              error_message: 'download ' + res.statusCode
            });
            // 纯音频 404＝B站 没给这条视频独立音轨（长视频常见）。
            // 这不是"失败"，是这条路走不通——告诉他声音在视频里，别让他对着按钮反复重试。
            if (kind === 'audio' && res.statusCode === 404) {
              this.setData({ audioUnavailable: true });
              toast('这条视频没有单独的音轨，可下载视频');
            } else {
              toast('下载失败');
            }
            return;
          }
          // 音频文件可能很大（如整场演唱会 Hi-Res），复制到 wx.env.USER_DATA_PATH
          // 会触发「本地用户文件 200MB 上限」，因此直接使用下载的临时文件路径分享。
          const persist = kind === 'audio'
            ? Promise.resolve(res.tempFilePath)
            : copyToNamed(res.tempFilePath, filename);
          persist.then((filePath) => {
            this.setData({ exports: completeExport(this.data.exports, kind, filePath) });
            this.reportDownload('download', 'success', { kind });
            toast('已下载，请点击保存');
            if (wx.vibrateShort) wx.vibrateShort({ type: 'light' });
          }).catch((err) => {
            this.setData({ exports: failExport(this.data.exports, kind) });
            this.reportDownload('download', 'fail', {
              kind,
              error_type: 'wx_error',
              error_message: (err && err.errMsg) || 'copy failed'
            });
            toast('下载失败');
          });
        },
        fail: (err) => {
          this.setData({ exports: failExport(this.data.exports, kind) });
          const domainBlocked = classifyError(null, err) === 'domain_not_configured';
          this.reportDownload('download', 'fail', {
            kind,
            error_type: domainBlocked ? 'domain_not_configured' : 'wx_error',
            error_message: (err && err.errMsg) || 'download failed'
          });
          // 抖音音频是 CDN 直链，域名没登记进微信白名单时只能复制链接去浏览器下载
          if (domainBlocked && this.data.isDouyin && kind === 'audio') {
            this.openExportFallback(kind);
            return;
          }
          toast('下载失败');
        }
      });
      task.onProgressUpdate((res) => {
        const written = formatSize(res.totalBytesWritten);
        const total = formatSize(res.totalBytesExpectedToWrite);
        const speed = this.computeDownloadSpeed(kind, res.totalBytesWritten);
        this.setData({
          exports: updateExportProgress(
            this.data.exports,
            kind,
            res.progress,
            [
              written && total ? written + '/' + total : '',
              speed
            ].filter(Boolean).join(' · ')
          )
        });
      });
    }).catch((err) => {
      this.setData({ exports: failExport(this.data.exports, kind) });
      this.reportDownload('download', 'fail', {
        kind,
        error_type: (err && err.code) === 'domain_not_configured' ? 'domain_not_configured' : 'wx_error',
        error_message: (err && err.message) || 'request failed'
      });
      if ((err && err.code) === 'domain_not_configured') {
        this.openExportFallback(kind);
        return;
      }
      toast('获取下载地址失败');
    });
  },

  // 抖音音频直连 CDN，域名没登记到微信白名单时小程序内根本下不动，
  // 这时给出一条「复制链接用浏览器打开」的路（B站 音频走后端中转，不会走到这）。
  // 按钮仍是「重试」，弹窗只是额外的一条路；复制的是重新取到的新直链，抖音直链有时效。
  openExportFallback(kind) {
    this.setData({ exports: failExport(this.data.exports, kind) });
    api.downloadUrl(this.data.cardId, kind).then((data) => {
      const list = data.candidates || [];
      const ready = configuredCandidates(list);
      const pick = (ready.length ? ready : list)[0];
      if (pick) {
        this.openFallback([pick]);
      }
    }).catch(() => {});
  },

  shareExport(kind) {
    const item = this.data.exports[kind];
    const filename = this.exportName(kind);
    shareFilePromise(item.path, filename).then(() => {
      this.setData({ exports: markExportSaved(this.data.exports, kind) });
      this.reportDownload('share', 'success', { kind });
      toast('已唤起文件分享');
    }).catch((err) => {
      const msg = (err && err.errMsg) || '分享失败';
      this.reportDownload('share', 'fail', { kind, error_type: 'wx_error', error_message: msg });
      toast(msg);
    });
  },

  computeDownloadSpeed(kind, bytes) {
    this._downloadSpeed = this._downloadSpeed || {};
    const now = Date.now();
    const state = this._downloadSpeed[kind];
    if (state && state.time && now - state.time >= 200 && bytes > state.bytes) {
      const speed = formatSpeed((bytes - state.bytes) / ((now - state.time) / 1000));
      state.bytes = bytes;
      state.time = now;
      state.speed = speed;
    } else if (!state) {
      this._downloadSpeed[kind] = { bytes: bytes, time: now, speed: '' };
    }
    return (this._downloadSpeed[kind] && this._downloadSpeed[kind].speed) || '';
  },

  reportDownload(stage, status, evt) {
    evt = evt || {};
    api.reportDownloadEvent({
      card_id: this.data.cardId,
      bvid: this.data.bvid,
      session_id: this._sessionId || '',
      kind: evt.kind || this.data.activeKind,
      qn: this.data.activeQn,
      host: evt.host || '',
      candidate_index: evt.candidate_index || 0,
      stage: stage,
      status: status,
      error_type: evt.error_type || '',
      error_message: evt.error_message || '',
      http_status: evt.http_status,
      wx_err_msg: evt.wx_err_msg || ''
    }).catch(() => {});
  },

  openFallback(candidates) {
    const first = (candidates && candidates[0]) || {};
    this.setData({
      fallbackVisible: true,
      fallbackUrl: first.url || ''
    });
  },

  onCloseFallback() {
    this.setData({ fallbackVisible: false });
  },

  onCopyFallback() {
    const url = this.data.fallbackUrl;
    if (!url) {
      toast('没有可复制的链接');
      return;
    }
    this.reportDownload('fallback', 'copy_link', {});
    wx.setClipboardData({ data: url, success() { toast('已复制，请用手机浏览器打开保存'); } });
  },

  onCopySub() {
    const lines = this.data.subtitles.map((s) => s.timeText + ' ' + s.text);
    if (!lines.length) { toast('无字幕'); return; }
    wx.setClipboardData({ data: lines.join('\n'), success() { toast('已复制'); } });
  },

  onOpenBili() {
    if (this.data.isDouyin) {
      this.onOpenDouyin();
      return;
    }
    const appId = getApp().globalData.biliMiniProgramAppId;
    if (!appId) {
      toast('B站小程序 appId 尚未配置');
      return;
    }
    wx.navigateToMiniProgram({ appId, path: '/pages/video/video?bvid=' + this.data.bvid });
  },

  // 分享出去的是"这一条视频的结果页"：卡片带标题和封面，路径带 bvid，
  // 别人点开就能直接看到（微信搜索爬虫也是从这类分享链接发现页面的）
  shareTitle() {
    const title = this.data.title || 'B站视频收藏';
    return this.data.origin ? title + ' · 原up主是谁' : title;
  },

  onShareAppMessage() {
    const path = this.data.isDouyin
      ? '/pages/result/result?platform=douyin&id=' + this.data.bvid
      : '/pages/result/result?bvid=' + this.data.bvid;
    return {
      title: this.shareTitle(),
      path,
      imageUrl: this.data.coverUrl
    };
  },

  onShareTimeline() {
    return {
      title: this.shareTitle(),
      query: this.data.isDouyin
        ? 'platform=douyin&id=' + this.data.bvid
        : 'bvid=' + this.data.bvid,
      imageUrl: this.data.coverUrl
    };
  }
});
