// 后端 API 地址：
// - 默认所有环境（开发/体验/审核/正式）都走备案域名，避免审核员拿到局域网 IP。
// - 本地联调时临时把 DEV_API_BASE 改成局域网地址，但不要提交/上传这种版本。
const PROD_API_BASE = 'https://api.beastnotes.cn';
const DEV_API_BASE = PROD_API_BASE;

function resolveApiBase() {
  let env = 'release';
  try {
    env = wx.getAccountInfoSync().miniProgram.envVersion || 'release';
  } catch (e) { /* 取不到环境信息时按正式版处理 */ }
  return env === 'trial' || env === 'release' ? PROD_API_BASE : DEV_API_BASE;
}

// 场景值 1129 = 微信搜索爬虫打开小程序
const SCENE_SEARCH_CRAWLER = 1129;

function queryString(query) {
  if (!query || typeof query !== 'object') {
    return '';
  }
  return Object.keys(query)
    .map((k) => k + '=' + query[k])
    .join('&');
}

App({
  globalData: {
    apiBase: resolveApiBase(),
    // B站官方小程序 appId（已配置 navigateToMiniProgramAppIdList）
    biliMiniProgramAppId: 'wx7564fd5313d24844'
  },

  // 爬虫访问时会带场景值 1129：上报一笔，管理端「搜索爬虫」页就能看到它来过
  onShow(options) {
    // 微信有时把 scene 传成字符串，统一转数字再比；顺便把真实值带给后端
    const scene = Number(options && options.scene) || 0;
    if (scene !== SCENE_SEARCH_CRAWLER) {
      return;
    }
    try {
      require('./utils/api.js').reportCrawlerVisit(
        options.path || '',
        queryString(options.query),
        scene
      );
    } catch (e) {
      // 上报失败不影响小程序使用
    }
  }
});
