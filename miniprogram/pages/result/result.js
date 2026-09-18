const api = require('../../utils/api.js');
const { formatDuration, formatDateTime } = require('../../utils/format.js');
const { downloadMedia, domainFromUrl } = require('../../utils/mediaDownload.js');

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
    media: { watermarked: false, clean: false, audio: false },
    features: { comment: true, danmaku: true },
    shareEnabled: true,
    subtitles: [],
    subPreview: [],
    showAllSub: false,
    danmakuCount: 0,
    previewing: false,
    srtLocalPath: '',
    danmakuLocalPath: '',
    audioLocalPath: '',
    mediaSize: {},
    downloading: false,
    downloadProgress: 0,
    downloadSizeText: '',
    fallbackVisible: false,
    fallbackUrl: '',
    fallbackMessage: '',
    tutorialVisible: false,
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
      media: r.media || { watermarked: false, clean: false, audio: false },
      features: r.features || { comment: true, danmaku: true },
      danmakuCount: r.danmaku_count || 0,
      subtitles,
      subPreview: subtitles.slice(0, 5)
    });
    this.prepareExports(r);
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

  prepareExports(r) {
    if (r.subtitles && r.subtitles.length) {
      this.prepareFile(api.exportFile(r.id, 'srt'), textFilename(r.title, r.bvid, '.srt'), 'srtLocalPath');
    }
    const features = r.features || { comment: true, danmaku: true };
    if (features.danmaku !== false && r.danmaku_count) {
      this.prepareFile(api.danmaku(r.id), textFilename(r.title, r.bvid, '_弹幕.txt'), 'danmakuLocalPath');
    }
  },

  prepareFile(downloadPromise, filename, key) {
    downloadPromise.then(({ url, header }) => {
      wx.downloadFile({
        url,
        header,
        success: (res) => {
          if (res.statusCode !== 200) {
            console.error('prepareFile download failed', key, res.statusCode, url);
            return;
          }
          copyToNamed(res.tempFilePath, filename).then((filePath) => {
            this.setData({ [key]: filePath });
          }).catch((err) => { console.error('prepareFile copy failed', key, err); });
        }
      });
    }).catch((err) => { console.error('prepareFile request failed', key, err); });
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

    downloadMedia(candidates, {
      report: (evt) => this.reportDownload(evt.stage, evt.status, evt)
    }).then((result) => {
      this.setData({ downloading: false });
      return copyToNamed(result.tempFilePath, filename)
        .then((filePath) => {
          if (kind === 'audio') {
            return shareFilePromise(filePath, filename).then(() => {
              this.reportDownload('share', 'success', { host: result.host });
              toast('已唤起文件分享');
            });
          }
          return saveVideoPromise(filePath).then(() => {
            this.reportDownload('save', 'success', { host: result.host });
            toast('已保存到相册');
          });
        })
        .catch((err) => {
          if (kind === 'audio') {
            return shareFilePromise(result.tempFilePath, filename).then(() => {
              this.reportDownload('share', 'success', { host: result.host });
              toast('已唤起文件分享');
            }).catch(() => {
              this.reportDownload('share', 'fail', {
                host: result.host,
                error_type: 'wx_error',
                error_message: '文件分享失败'
              });
              this.openFallback(candidates, '文件分享失败，可复制链接后手动保存');
            });
          }
          return saveVideoPromise(result.tempFilePath).then(() => {
            this.reportDownload('save', 'success', { host: result.host });
            toast('已保存到相册');
          }).catch((saveErr) => {
            this.reportDownload('save', 'fail', {
              host: result.host,
              error_type: 'permission',
              error_message: (saveErr && saveErr.errMsg) || '保存失败'
            });
            this.openFallback(candidates, '保存到相册失败，可在设置中允许保存到相册');
          });
        });
    }).catch((err) => {
      this.setData({ downloading: false });
      this.openFallback(candidates, (err && err.message) || '下载失败');
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
            this.reportDownload('resolve', 'success', {});
            this.saveMedia(data.candidates, kind);
          }).catch(() => {
            this.reportDownload('resolve', 'fail', { error_type: 'unknown', error_message: '获取下载地址失败' });
            toast('获取下载地址失败');
          });
        }
      });
    }).catch(() => {
      this.reportDownload('resolve', 'fail', { error_type: 'unknown', error_message: '获取清晰度失败' });
      toast('获取清晰度失败');
    });
  },

  onDownloadAudio() {
    const kind = 'audio';
    this.setData({ activeKind: kind, activeQn: null });
    api.downloadUrl(this.data.cardId, kind).then((data) => {
      this.reportDownload('resolve', 'success', {});
      this.saveMedia(data.candidates, kind);
    }).catch(() => {
      this.reportDownload('resolve', 'fail', { error_type: 'unknown', error_message: '获取下载地址失败' });
      toast('获取下载地址失败');
    });
  },

  reportDownload(stage, status, evt) {
    evt = evt || {};
    api.reportDownloadEvent({
      card_id: this.data.cardId,
      bvid: this.data.bvid,
      kind: this.data.activeKind,
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

  openFallback(candidates, message) {
    const first = (candidates && candidates[0]) || {};
    this.setData({
      fallbackVisible: true,
      fallbackUrl: first.url || '',
      fallbackMessage: message || '下载失败'
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
    wx.setClipboardData({ data: url, success() { toast('已复制，请立即使用'); } });
  },

  onShowTutorial() {
    this.setData({ fallbackVisible: false, tutorialVisible: true });
  },

  onCloseTutorial() {
    this.setData({ tutorialVisible: false });
  },

  onRetryDownload() {
    this.setData({ fallbackVisible: false });
    const bvid = this.data.bvid;
    if (bvid) {
      this.loadByBvid(bvid);
    }
  },

  onToggleSub() {
    this.setData({ showAllSub: !this.data.showAllSub });
  },

  onCopySub() {
    const lines = this.data.subtitles.map((s) => s.timeText + ' ' + s.text);
    if (!lines.length) { toast('无字幕'); return; }
    wx.setClipboardData({ data: lines.join('\n'), success() { toast('已复制'); } });
  },

  onDownloadSrt() {
    const filename = textFilename(this.data.title, this.data.bvid, '.srt');
    if (this.data.srtLocalPath) {
      shareLocalFile(this.data.srtLocalPath, filename);
    } else {
      toast('文件准备中，请稍后重试');
    }
  },

  onDownloadDanmaku() {
    const filename = textFilename(this.data.title, this.data.bvid, '_弹幕.txt');
    if (this.data.danmakuLocalPath) {
      shareLocalFile(this.data.danmakuLocalPath, filename);
    } else {
      toast('文件准备中，请稍后重试');
    }
  },

  onDownloadComments() {
    const filename = textFilename(this.data.title, this.data.bvid, '_评论.txt');
    wx.showLoading({ title: '加载评论中' });
    api.comments(this.data.cardId).then(({ url, header }) => {
      wx.downloadFile({
        url,
        header,
        success: (res) => {
          wx.hideLoading();
          if (res.statusCode !== 200) { toast('下载失败'); return; }
          copyToNamed(res.tempFilePath, filename).then((filePath) => {
            shareLocalFile(filePath, filename);
          }).catch(() => shareLocalFile(res.tempFilePath, filename));
        },
        fail: () => { wx.hideLoading(); toast('下载失败'); }
      });
    }).catch(() => { wx.hideLoading(); toast('加载评论失败'); });
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
