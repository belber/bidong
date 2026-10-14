const TOKEN_KEY = 'bili_access_token';

function baseUrl() {
  return getApp().globalData.apiBase;
}

// 封面等媒体地址：本地存储后端返回的是相对路径（/media/covers/x.jpg），
// 用 apiBase 拼成当前环境能访问的地址；COS（生产）返回的是绝对地址，原样使用。
// 这样开发版换 IP 不用改数据库，生产行为完全不变。
function resolveMediaUrl(value) {
  if (!value || typeof value !== 'string') {
    return value;
  }
  if (/^(https?:)?\/\//i.test(value) || value.indexOf('data:') === 0) {
    return value;
  }
  let base = '';
  try {
    base = baseUrl() || '';
  } catch (err) {
    base = ''; // 取不到环境地址时退回原值，别把图片地址拼坏
  }
  if (!base) {
    return value;
  }
  return base.replace(/\/+$/, '') + '/' + value.replace(/^\/+/, '');
}

function login() {
  return new Promise((resolve, reject) => {
    wx.login({
      success(res) {
        if (!res.code) {
          reject(new Error('获取微信登录凭证失败'));
          return;
        }
        wx.request({
          url: baseUrl() + '/api/login',
          method: 'POST',
          data: { code: res.code },
          success(r) {
            if (r.statusCode === 200 && r.data && r.data.access_token) {
              wx.setStorageSync(TOKEN_KEY, r.data.access_token);
              resolve(r.data.access_token);
            } else {
              reject(new Error((r.data && r.data.message) || '登录失败'));
            }
          },
          fail(err) {
            reject(new Error(err.errMsg || '登录请求失败'));
          }
        });
      },
      fail(err) {
        reject(new Error(err.errMsg || '微信登录失败'));
      }
    });
  });
}

function ensureToken() {
  const token = wx.getStorageSync(TOKEN_KEY);
  if (token) {
    return Promise.resolve(token);
  }
  return login();
}

function requestError(statusCode, data, fallback) {
  const err = new Error((data && data.message) || fallback || ('请求失败 ' + statusCode));
  err.statusCode = statusCode;
  err.data = data || null;
  return err;
}

function request(method, path, data) {
  const doRequest = (token) =>
    new Promise((resolve, reject) => {
      const header = token ? { Authorization: 'Bearer ' + token } : {};
      wx.request({
        url: baseUrl() + path,
        method,
        data,
        header,
        success(r) {
          if (r.statusCode === 401) {
            login()
              .then((newToken) => doRequest(newToken).then(resolve, reject))
              .catch(reject);
            return;
          }
          if (r.statusCode >= 200 && r.statusCode < 300) {
            resolve(r.data);
          } else {
            reject(requestError(r.statusCode, r.data));
          }
        },
        fail(err) {
          reject(new Error(err.errMsg || '网络请求失败'));
        }
      });
    });

  return ensureToken().then(doRequest);
}

function buildQuery(params) {
  if (!params) {
    return '';
  }
  const parts = Object.keys(params)
    .filter((k) => params[k] !== undefined && params[k] !== null && params[k] !== '')
    .map((k) => encodeURIComponent(k) + '=' + encodeURIComponent(params[k]));
  return parts.length ? '?' + parts.join('&') : '';
}

function fileDownload(path) {
  return ensureToken().then((token) => ({
    url: baseUrl() + path,
    header: token ? { Authorization: 'Bearer ' + token } : {}
  }));
}

function authHeader() {
  const token = wx.getStorageSync(TOKEN_KEY);
  return token ? { Authorization: 'Bearer ' + token } : {};
}

function publicRequest(method, path, data) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: baseUrl() + path,
      method,
      data,
      success(r) {
        if (r.statusCode === 200 && r.data) {
          resolve(r.data);
        } else {
          reject(new Error((r.data && r.data.message) || ('请求失败 ' + r.statusCode)));
        }
      },
      fail(err) {
        reject(new Error(err.errMsg || '网络请求失败'));
      }
    });
  });
}

module.exports = {
  resolveMediaUrl,
  parse(url) {
    return request('POST', '/api/parse', { url });
  },
  getCards(params) {
    return request('GET', '/api/cards' + buildQuery(params));
  },
  getCard(id) {
    return request('GET', '/api/cards/' + id);
  },
  deleteCard(id) {
    return request('DELETE', '/api/cards/' + id);
  },
  getTags() {
    return request('GET', '/api/tags');
  },
  createTag(name) {
    return request('POST', '/api/tags', { name });
  },
  addCardTags(id, tags) {
    return request('POST', '/api/cards/' + id + '/tags', { tags });
  },
  bind(code) {
    return request('POST', '/api/binding', { code });
  },
  getBinding() {
    return request('GET', '/api/binding');
  },
  getHelpConfig() {
    return publicRequest('GET', '/api/help/config');
  },
  getPublicConfig() {
    return publicRequest('GET', '/api/config/public');
  },
  // 免登录的视频信息：结果页被分享/被爬虫打开时用（没有登录态也能看到内容）
  getPublicCard(bvid) {
    return publicRequest('GET', '/api/public/cards/' + bvid);
  },
  // 微信搜索爬虫打开页面时会带场景值 1129：上报一笔，管理端就能看到"爬虫来过"
  reportCrawlerVisit(path, query) {
    return publicRequest('POST', '/api/public/crawler-visit', {
      path: path || '',
      query: query || '',
      scene: 1129
    });
  },
  unbind() {
    return request('DELETE', '/api/binding');
  },
  mediaOptions(id, kind) {
    return request('GET', '/api/cards/' + id + '/media-options?kind=' + encodeURIComponent(kind));
  },
  download(id, kind, qn) {
    const suffix = qn ? '&qn=' + qn : '';
    return fileDownload('/api/cards/' + id + '/download?kind=' + kind + suffix);
  },
  authHeader() {
    return authHeader();
  },
  downloadUrl(id, kind, qn) {
    const suffix = qn ? '&qn=' + qn : '';
    // 抖音图文要一次拿全部图片，index=0 表示「从这个位置开始给整组」
    const idx = arguments.length > 3 && arguments[3] ? '&index=' + arguments[3] : '';
    return request('GET', '/api/cards/' + id + '/download-url?kind=' + kind + suffix + idx);
  },
  reportDownloadEvent(payload) {
    return request('POST', '/api/download-events', payload);
  },
  reportVisit(path) {
    return request('POST', '/api/visit-events', { path });
  },
  mediaSize(id) {
    return request('GET', '/api/cards/' + id + '/media-size');
  },
  danmaku(id) {
    return fileDownload('/api/cards/' + id + '/danmaku');
  },
  comments(id) {
    return fileDownload('/api/cards/' + id + '/comments');
  },
  exportFile(id, kind) {
    return fileDownload('/api/cards/' + id + '/export?kind=' + kind);
  }
};
