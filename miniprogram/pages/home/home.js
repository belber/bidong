const { extractLink } = require('../../utils/parse.js');
const api = require('../../utils/api.js');
const { AD_UNIT_IDS } = require('../../utils/ads.js');

const DEMO_LINK = 'https://b23.tv/2g9l5YF';
// 输入框里放一条真实的分享文案做示例：比「粘贴链接」这种说明性文案更容易让人照做
const DEMO_PLACEHOLDER =
  '【高校妖娆版【极乐净土】与原舞蹈对比版！！！-哔哩哔哩】 ' + DEMO_LINK;
const PLATFORM_LABEL = { bilibili: 'B站', douyin: '抖音' };

Page(Object.assign({
  data: {
    input: '',
    demoPlaceholder: DEMO_PLACEHOLDER,
    // 识别到的平台，输入框右下角亮出来，让用户确认贴对了
    platform: '',
    platformLabel: '',
    parsing: false,
    showRobotGuide: true,
    homeAdUnitId: AD_UNIT_IDS.homeBanner,
    homeAdError: false
  },

  onShow() {
    if (this.data.parsing) {
      this.setData({ parsing: false });
    }
    if (this.getTabBar) {
      this.getTabBar().setData({ selected: 0 });
    }
    this.loadUiConfig();
    this.trackVisit();
  },

  onHomeAdError(e) {
    console.warn('[ad] 首页横幅加载失败', e && e.detail);
    this.setData({ homeAdError: true });
  },

  trackVisit() {
    const d = new Date();
    const today = d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate();
    if (wx.getStorageSync('visit_reported_date') === today) {
      return;
    }
    api.reportVisit('pages/home/home').then(() => {
      wx.setStorageSync('visit_reported_date', today);
    }).catch(() => {});
  },

  loadUiConfig() {
    api
      .getPublicConfig()
      .then((cfg) => {
        this.setData({ showRobotGuide: cfg.robot_guide !== false });
      })
      .catch(() => {});
  },

  onPaste() {
    wx.getClipboardData({
      success: (res) => {
        const text = (res.data || '').trim();
        const found = extractLink(text);
        if (!found) {
          wx.showToast({ title: '剪贴板里没有 B站 或抖音视频链接', icon: 'none' });
          return;
        }
        this.setData({
          input: text,
          platform: found.platform,
          platformLabel: PLATFORM_LABEL[found.platform] || ''
        });
      }
    });
  },

  onInput(e) {
    const value = e.detail.value;
    const found = extractLink(value);
    this.setData({
      input: value,
      platform: found ? found.platform : '',
      platformLabel: found ? PLATFORM_LABEL[found.platform] : ''
    });
  },

  onParse() {
    if (this.data.parsing) {
      return;
    }
    const raw = (this.data.input || '').trim();
    const text = raw || DEMO_LINK;
    const found = extractLink(text);
    if (!found) {
      wx.showToast({ title: '请输入 B站 或抖音视频链接', icon: 'none' });
      return;
    }
    const link = found.link;
    this.setData({ parsing: true });
    const minWait = new Promise((resolve) => setTimeout(resolve, 700));
    const parseReq = api.parse(link.url);
    Promise.all([parseReq, minWait])
      .then(([card]) => {
        getApp().globalData.pendingResult = card;
        wx.setStorageSync('pending_result', card);
        // 带上 bvid：这样结果页的 URL 是自包含的（可分享、可被微信搜索爬虫直接打开），
        // 不再依赖 globalData / storage 传参
        const target = (card.platform === 'douyin')
          ? '/pages/result/result?platform=douyin&id=' + card.bvid
          : '/pages/result/result?bvid=' + card.bvid;
        wx.navigateTo({ url: target });
      })
      .catch((err) => {
        this.setData({ parsing: false });
        wx.showToast({ title: err.message || '解析失败', icon: 'none' });
      });
  }
}, require("../../utils/share.js").pageShare));
