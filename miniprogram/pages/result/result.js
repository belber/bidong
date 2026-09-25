const api = require('../../utils/api.js');
const { formatDuration, formatDateTime } = require('../../utils/format.js');
const { mapOrigin } = require('../../utils/origin.js');
const { downloadMediaParallel, downloadUrlErrorType, configuredCandidates } = require('../../utils/mediaDownload.js');
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
    activeQn: null
  },

  onLoad(options) {
    this.loadUiConfig();
    const bvid = (options && options.bvid) || '';
    if (bvid) {
      this.loadByBvid(bvid);
      return;
    }
    this.applyResult(getApp().globalData.pendingResult || wx.getStorageSync('pending_result'));
  },

  loadUiConfig() {
    api
      .getPublicConfig()
      .then((cfg) => {
        this.setData({ shareEnabled: cfg.share !== false });
      })
      .catch(() => {});
  },

  loadByBvid(bvid) {
    wx.showLoading({ title: '加载中' });
    api.parse('https://www.bilibili.com/video/' + bvid)
      .then((card) => {
        wx.hideLoading();
        getApp().globalData.pendingResult = card;
        wx.setStorageSync('pending_result', card);
        this.applyResult(card);
      })
      .catch((err) => {
        wx.hideLoading();
        toast(err.message || '加载失败');
      });
  },

  applyResult(r) {
    if (!r) {
      toast('暂无解析数据');
      return;
    }
    const subtitles = (r.subtitles || []).map((s) => ({
      t: s.t,
      text: s.text,
      timeText: formatDuration(s.t)
    }));
    const tags = Array.isArray(r.tags) ? r.tags : [];
    this.setData({
      cardId: r.id,
      bvid: r.bvid,
      sourceUrl: r.source_url,
      title: r.title,
      upName: r.up_name,
      partition: r.partition || '',
      pubText: formatDateTime(r.pubdate),
      tags,
      tagsText: tags.join(' '),
      desc: r.desc,
      stats: r.stats || { like: 0, reply: 0, favorite: 0, coin: 0 },
      coverUrl: r.cover_url,
      origin: mapOrigin(r.origin),
      media: r.media || { watermarked: false, clean: false, audio: false },
      features: r.features || { comment: true, danmaku: true },
      danmakuCount: r.danmaku_count || 0,
      subtitles,
      subPreview: subtitles.slice(0, 5),
      exports: initialExports()
    });
    this.loadMediaSize(r.id);
  },

  loadMediaSize(cardId) {
    api.mediaSize(cardId).then((sizes) => {
      const labels = {};
      if (sizes.watermarked) labels.watermarked = '约 ' + formatSize(sizes.watermarked);
      if (sizes.clean) labels.clean = '约 ' + formatSize(sizes.clean);
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

  onCopyTag(e) {
    this.copy(e.currentTarget.dataset.field);
  },

  // 只复制原作者主页：抖音/X 的链接在小程序里打不开，复制到浏览器看
  onCopyAuthorHome() {
    const origin = this.data.origin;
    const url = origin && origin.authorUrl;
    if (!url) {
      toast('没有可复制的主页');
      return;
    }
    wx.setClipboardData({
      data: url,
      success() { toast('主页链接已复制'); }
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
            toast('下载失败');
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
          this.reportDownload('download', 'fail', {
            kind,
            error_type: 'wx_error',
            error_message: (err && err.errMsg) || 'download failed'
          });
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
        error_type: 'wx_error',
        error_message: (err && err.message) || 'request failed'
      });
      toast('获取下载地址失败');
    });
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
    const appId = getApp().globalData.biliMiniProgramAppId;
    if (!appId) {
      toast('B站小程序 appId 尚未配置');
      return;
    }
    wx.navigateToMiniProgram({ appId, path: '/pages/video/video?bvid=' + this.data.bvid });
  },

  onShareAppMessage() {
    return {
      title: this.data.title || 'B站视频收藏',
      path: '/pages/result/result?bvid=' + this.data.bvid,
      imageUrl: this.data.coverUrl
    };
  }
});
