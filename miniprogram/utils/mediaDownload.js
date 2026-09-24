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

// download-url 阶段失败时区分：
// - 后端明确返回 error_type（例如 domain_not_registered）时直接采用
// - 其他 HTTP 错误归为 http_error
// - 网络/未知错误归为 unknown
function downloadUrlErrorType(err) {
  if (err && err.data && err.data.error_type) {
    return err.data.error_type;
  }
  if (err && err.statusCode && err.statusCode >= 400) {
    return 'http_error';
  }
  return 'unknown';
}

function configuredCandidates(candidates) {
  return (candidates || []).filter((candidate) => candidate && candidate.configured);
}

function startDownloadAttempt(item, index, options) {
  let abort = function () {};
  const promise = new Promise(function (resolve) {
    const task = wx.downloadFile({
      url: item.url,
      header: options.header || {},
      // 视频文件较大，放长到 30 分钟，避免默认 60 秒超时把下载掐断。
      timeout: options.timeout || 1800000,
      success: function (res) {
        if (res.statusCode === 200) {
          if (options.report) {
            options.report({
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
          resolve({ tempFilePath: res.tempFilePath, host: item.host, candidateIndex: index });
        } else {
          const errMsg = (res.errMsg || res.error || '') || '';
          if (options.report) {
            options.report({
              stage: 'download',
              status: 'fail',
              host: item.host,
              candidate_index: index,
              error_type: classifyError(res.statusCode, { errMsg: errMsg }),
              error_message: errMsg,
              http_status: res.statusCode,
              wx_err_msg: errMsg
            });
          }
          resolve(null);
        }
      },
      fail: function (err) {
        const errMsg = (err && err.errMsg) || '';
        if (options.report) {
          options.report({
            stage: 'download',
            status: 'fail',
            host: item.host,
            candidate_index: index,
            error_type: classifyError(null, err),
            error_message: errMsg,
            http_status: null,
            wx_err_msg: errMsg
          });
        }
        resolve(null);
      }
    });
    if (task && typeof task.abort === 'function') {
      abort = function () { task.abort(); };
    }
    if (task && typeof task.onProgressUpdate === 'function' && options.onProgress) {
      task.onProgressUpdate(function (res) {
        options.onProgress(res, index);
      });
    }
  });
  return { promise: promise, abort: abort };
}

// 并发下载多个候选地址，任一成功即返回，其余任务会被取消。
// 相比逐个顺序重试，能更快避开慢速或过期的 CDN 节点。
function downloadMediaParallel(candidates, options) {
  const list = (candidates || []).slice();
  const opts = options || {};
  if (!list.length) {
    return Promise.reject({ allFailed: true, message: '没有可用的下载地址' });
  }

  return new Promise(function (resolve, reject) {
    let settled = false;
    let pending = list.length;
    const attempts = list.map(function (item, index) {
      const attemptOpts = Object.assign({}, opts);
      if (opts.onProgress) {
        const latest = []; // 每个候选最近一次进度
        attemptOpts.onProgress = function (res, candidateIndex) {
          latest[candidateIndex] = res;
          let best = -1;
          let bestIndex = 0;
          for (let i = 0; i < list.length; i += 1) {
            const cur = latest[i];
            if (cur && typeof cur.progress === 'number' && cur.progress > best) {
              best = cur.progress;
              bestIndex = i;
            }
          }
          if (best > -1) {
            opts.onProgress(latest[bestIndex], bestIndex);
          }
        };
      }
      if (opts.report) {
        const report = opts.report;
        attemptOpts.report = function (evt) {
          if (!settled) {
            report(evt);
          }
        };
      }
      return startDownloadAttempt(item, index, attemptOpts);
    });

    attempts.forEach(function (attempt, current) {
      attempt.promise.then(function (result) {
        if (settled) {
          return;
        }
        if (result) {
          settled = true;
          attempts.forEach(function (other, i) {
            if (i !== current) {
              other.abort();
            }
          });
          resolve(result);
          return;
        }
        pending -= 1;
        if (pending === 0) {
          settled = true;
          reject({ allFailed: true, message: '所有下载地址均失败' });
        }
      });
    });
  });
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
    if (opts.onProgress) {
      opts.onProgress({ progress: 0, totalBytesWritten: 0, totalBytesExpectedToWrite: 0 }, index);
    }
    return new Promise(function (resolve) {
      const task = wx.downloadFile({
        url: item.url,
        header: opts.header || {},
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
      if (task && typeof task.onProgressUpdate === 'function' && opts.onProgress) {
        task.onProgressUpdate(function (res) {
          opts.onProgress(res, index);
        });
      }
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
  configuredCandidates,
  domainFromUrl,
  downloadUrlErrorType,
  downloadMedia,
  downloadMediaParallel
};
