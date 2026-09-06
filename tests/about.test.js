describe('about page UI config', () => {
  let page;
  let mockGetPublicConfig;

  function loadPage() {
    let captured;
    global.Page = (config) => {
      captured = config;
      captured.setData = jest.fn((patch) => {
        captured.data = Object.assign({}, captured.data, patch);
      });
    };
    jest.resetModules();
    jest.mock('../miniprogram/utils/api.js', () => ({
      getPublicConfig: mockGetPublicConfig
    }));
    require('../miniprogram/pages/about/about.js');
    return captured;
  }

  beforeEach(() => {
    mockGetPublicConfig = jest.fn();
    global.Page = undefined;
  });

  afterEach(() => {
    delete global.Page;
    jest.dontMock('../miniprogram/utils/api.js');
  });

  it('shows the robot highlight by default', () => {
    mockGetPublicConfig.mockResolvedValue({ robot_guide: true, share: true });
    page = loadPage();

    expect(page.data.showRobotGuide).toBe(true);

    return page.loadUiConfig().then(() => {
      expect(mockGetPublicConfig).toHaveBeenCalledTimes(1);
      expect(page.data.showRobotGuide).toBe(true);
    });
  });

  it('hides the robot highlight when the switch is off', () => {
    mockGetPublicConfig.mockResolvedValue({ robot_guide: false, share: true });
    page = loadPage();

    return page.loadUiConfig().then(() => {
      expect(page.data.showRobotGuide).toBe(false);
    });
  });
});
