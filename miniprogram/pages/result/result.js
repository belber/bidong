const api = require('../../utils/api.js');
const { formatDuration, formatDateTime } = require('../../utils/format.js');

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
    subtitles: [],
    subPreview: [],
    showAllSub: false,
    danmakuCount: 0,
    previewing: false,
    srtLocalPath: '',
    danmakuLocalPath: '',
    audioLocalPath: ''
  },

  onLoad(options) {
    const bvid = (options && options.bvid) || '';
    if (bvid) {
      this.loadByBvid(bvid);
      return;
    }
    this.applyResult(getApp().globalData.pendingResult || wx.getStorageSync('pending_result'));
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
      danmakuCount: r.danmaku_count || 0,
      subtitles,
      subPreview: subtitles.slice(0, 5)
    });
    this.prepareExports(r);
  },

  prepareExports(r) {
    if (r.subtitles && r.subtitles.length) {
      this.prepareFile(api.exportFile(r.id, 'srt'), textFilename(r.title, r.bvid, '.srt'), 'srtLocalPath');
    }
    if (r.danmaku_count) {
      this.prepareFile(api.danmaku(r.id), textFilename(r.title, r.bvid, '_弹幕.txt'), 'danmakuLocalPath');
    }
    if (r.media && r.media.audio) {
      this.prepareFile(api.download(r.id, 'audio'), mediaFilename(r.title, r.bvid, 'audio'), 'audioLocalPath');
    }
  },

  prepareFile(downloadPromise, filename, key) {
    downloadPromise.then(({ url, header }) => {
      wx.downloadFile({
        url,
        header,
        success: (res) => {
          if (res.statusCode !== 200) { return; }
          copyToNamed(res.tempFilePath, filename).then((filePath) => {
            this.setData({ [key]: filePath });
          }).catch(() => {});
        }
      });
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

  saveMedia(url, header) {
    wx.showLoading({ title: '下载中' });
    wx.downloadFile({
      url,
      header,
      success(res) {
        wx.hideLoading();
        if (res.statusCode !== 200) { toast('下载失败'); return; }
        saveToAlbum(wx.saveVideoToPhotosAlbum, res.tempFilePath);
      },
      fail() { wx.hideLoading(); toast('下载失败'); }
    });
  },

  onDownloadVideo(e) {
    const kind = e.currentTarget.dataset.kind;
    api.mediaOptions(this.data.cardId, kind).then((options) => {
      if (!options.length) {
        toast('无可用清晰度');
        return;
      }
      wx.showActionSheet({
        itemList: options.map((o) => o.label),
        success: (res) => {
          const chosen = options[res.tapIndex];
          api.download(this.data.cardId, kind, chosen.qn).then(({ url, header }) => {
            this.saveMedia(url, header);
          }).catch(() => toast('下载失败'));
        }
      });
    }).catch(() => toast('获取清晰度失败'));
  },

  onDownloadAudio() {
    const filename = mediaFilename(this.data.title, this.data.bvid, 'audio');
    if (this.data.audioLocalPath) {
      shareLocalFile(this.data.audioLocalPath, filename);
    } else {
      toast('文件准备中，请稍后重试');
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
