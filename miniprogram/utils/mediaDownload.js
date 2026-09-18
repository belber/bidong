function domainFromUrl(url) {
  if (!url) {
    return '';
  }
  const m = String(url).match(/^https?:\/\/([^/:]+)/);
  return m ? m[1] : '';
}

function classifyError(statusCode, err) {
  const msg = (err && err.errMsg) || '';
  if (/url not in domain list|url not in domain|downloadFile:fail url not/i.test(msg)) {
    return 'domain_not_configured';
  }
  if (statusCode === 403) {
    return 'expired';
  }
  if (statusCode && statusCode >= 400) {
    return 'http_error';
  }
  if (msg) {
    return 'wx_error';
  }
  return 'unknown';
}

function downloadMedia(candidates, options) {
  const queue = (candidates || []).slice();
  const opts = options || {};

  function reportSuccess(item, index) {
    if (opts.report) {
      opts.report({
        stage: 'download',
        status: 'success',
        host: item.host,
        candidate_index: index,
        error_type: '',
        error_message: '',
        http_status: 200,
        wx_err_msg: ''
      });
    }
  }

  function reportFail(item, index, errorType, statusCode, message) {
    if (opts.report) {
      opts.report({
        stage: 'download',
        status: 'fail',
        host: item.host,
        candidate_index: index,
        error_type: errorType,
        error_message: message || '',
        http_status: statusCode,
        wx_err_msg: message || ''
      });
    }
  }

  function attempt(index) {
    if (index >= queue.length) {
      return Promise.reject({ allFailed: true, message: '所有下载地址均失败' });
    }
    const item = queue[index];
    return new Promise(function (resolve) {
      wx.downloadFile({
        url: item.url,
        success: function (res) {
          if (res.statusCode === 200) {
            reportSuccess(item, index);
            resolve({
              tempFilePath: res.tempFilePath,
              host: item.host,
              candidateIndex: index
            });
          } else {
            const errMsg = (res.errMsg || res.error || '') || '';
            reportFail(item, index, classifyError(res.statusCode, { errMsg: errMsg }), res.statusCode, errMsg);
            resolve(null);
          }
        },
        fail: function (err) {
          reportFail(item, index, classifyError(null, err), null, (err && err.errMsg) || '');
          resolve(null);
        }
      });
    }).then(function (result) {
      if (result) {
        return result;
      }
      return attempt(index + 1);
    });
  }

  return attempt(0);
}

module.exports = {
  classifyError,
  domainFromUrl,
  downloadMedia
};
