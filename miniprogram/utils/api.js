const TOKEN_KEY = 'bili_access_token';

function baseUrl() {
  return getApp().globalData.apiBase;
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
            reject(new Error((r.data && r.data.message) || ('请求失败 ' + r.statusCode)));
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

module.exports = {
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
  }
};

