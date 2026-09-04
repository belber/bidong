// 后端 API 地址按环境自动选择：
// - 开发版（开发者工具模拟器 / 真机调试）：本地 127.0.0.1，需勾选「不校验合法域名」
// - 体验版 / 正式版：必须用已备案的 HTTPS 域名，且要在公众平台配置 request 合法域名
const DEV_API_BASE = 'http://127.0.0.1:8000';
// TODO: 拿到备案域名后替换为正式地址，并在微信公众平台配置 request 合法域名
const PROD_API_BASE = 'https://api.beastnotes.cn';

function resolveApiBase() {
  let env = 'develop';
  try {
    env = wx.getAccountInfoSync().miniProgram.envVersion;
  } catch (e) { /* 基础库过低等异常时退回开发地址 */ }
  return env === 'trial' || env === 'release' ? PROD_API_BASE : DEV_API_BASE;
}

App({
  globalData: {
    apiBase: resolveApiBase(),
    // B站官方小程序 appId（已配置 navigateToMiniProgramAppIdList）
    biliMiniProgramAppId: 'wx7564fd5313d24844'
  }
});
