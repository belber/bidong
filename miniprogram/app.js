App({
  globalData: {
    // 后端 API 地址：本地联调用 127.0.0.1；上线前替换为备案域名。
    // 开发者工具需勾选「详情 -> 本地设置 -> 不校验合法域名」。
    apiBase: 'http://127.0.0.1:8000',
    // B站官方小程序 appId（已配置 navigateToMiniProgramAppIdList）
    biliMiniProgramAppId: 'wx7564fd5313d24844'
  }
});
