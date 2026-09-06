const api = require('../../utils/api.js');

Page({
  data: {
    showRobotGuide: true
  },

  onShow() {
    this.loadUiConfig();
  },

  loadUiConfig() {
    return api
      .getPublicConfig()
      .then((cfg) => {
        this.setData({ showRobotGuide: cfg.robot_guide !== false });
      })
      .catch(() => {});
  }
});
