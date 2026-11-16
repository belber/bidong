const api = require('../../utils/api');
const transcriptClient = require('../../utils/transcript');
const {formatDuration} = require('../../utils/format');
const yuanbao = require('../../utils/yuanbao');
function toast(title) { wx.showToast({title,icon:'none'}); }
function decode(value) { try {return decodeURIComponent(value || '');} catch(e) {return '';} }
Page({
  data: {cardId:0,title:'',author:'',durationText:'',languageText:'',tab:'timeline',lines:[],plainText:'',
    transcript:transcriptClient.decorate(),transcriptReadError:'',exportState:'idle',exportPath:'',exportName:'',
    canSummarize:false,summaryVisible:false,summaryCopying:false,summaryOpening:false},
  onLoad(options) {
    const id=Number(options.id);
    this.setData({cardId:Number.isInteger(id) && id>0 ? id:0,title:decode(options.title),author:decode(options.author),
      durationText:formatDuration(Number(options.duration)||0)});
    if(!this.data.cardId) toast('视频信息无效，请返回重试');
  },
  onShow() {this._transcriptVisible=true;transcriptClient.refresh(this);},
  onHide() {transcriptClient.stop(this);this.onCloseSummary();},
  onUnload() {transcriptClient.stop(this);this.onCloseSummary();if(this._exportTask) this._exportTask.abort();},
  onTranscriptUpdate(value) {
    const lines=(value.segments || []).map(s => Object.assign({},s,{timeText:formatDuration(s.start)}));
    const plainText = lines.map(s => s.text).join('\n');
    const canSummarize = value.status === 'completed' && !!plainText.trim();
    if (plainText !== this.data.plainText || !canSummarize) this.onCloseSummary();
    this.setData({lines,plainText,canSummarize,languageText:value.language === 'zh' ? '中文':(value.language || '')});
  },
  onOpenSummary() {
    if (!this.data.canSummarize || this.data.summaryCopying || this.data.summaryOpening || this.data.summaryVisible) return;
    this.onCloseSummary();
    const epoch = this._summaryEpoch;
    this.setData({summaryCopying:true});
    wx.setClipboardData({data:yuanbao.summaryText(this.data.plainText),
      success:() => {
        if (epoch !== this._summaryEpoch) return;
        this.setData({summaryCopying:false,summaryVisible:true});
      },
      fail:() => {
        if (epoch !== this._summaryEpoch) return;
        this.onCloseSummary();
        toast('复制未完成，请重试');
      }
    });
  },
  onCloseSummary() {
    // 取消、离开或正文变化后，不允许迟到的复制回调重新弹框。
    this._summaryEpoch = (this._summaryEpoch || 0) + 1;
    this.setData({summaryVisible:false,summaryCopying:false,summaryOpening:false});
  },
  onSummaryTouchMove() {},
  onOpenYuanbao() {
    if (!this.data.summaryVisible || !this.data.canSummarize || this.data.summaryOpening) return;
    const epoch = this._summaryEpoch;
    const failed = () => {
      if (epoch !== this._summaryEpoch) return;
      this.onCloseSummary();
      wx.showModal({title:'暂时无法打开元宝',content:'文案已复制，可在微信搜索“元宝”，粘贴已复制内容。',showCancel:false,confirmText:'知道了'});
    };
    if (!wx.navigateToMiniProgram) return failed();
    this.setData({summaryOpening:true});
    // 确认按钮直接触发跳转，保留微信要求的用户点击手势。
    try {
      wx.navigateToMiniProgram({appId:yuanbao.APP_ID,envVersion:'release',
        success:() => {if (epoch === this._summaryEpoch) this.onCloseSummary();},
        fail:err => {
          if (epoch !== this._summaryEpoch) return;
          if (/cancel/i.test(err.errMsg || '')) this.onCloseSummary();
          else failed();
        },
        complete:() => {if (epoch === this._summaryEpoch) this.setData({summaryOpening:false});}
      });
    } catch (err) { failed(); }
  },
  onTab(e) {this.setData({tab:e.currentTarget.dataset.tab === 'plain' ? 'plain':'timeline'});},
  onCopyText() {
    if(!this.data.plainText) return toast('文案尚未完成');
    wx.setClipboardData({data:this.data.plainText,success:()=>toast('已复制全文'),fail:()=>toast('复制未完成，请尝试导出TXT')});
  },
  onRetryRead() {this.setData({transcriptReadError:''});return transcriptClient.refresh(this);},
  onExportTxt() {
    if(this.data.exportState === 'ready') {
      if(!wx.shareFileMessage) return toast('当前微信版本不支持文件分享');
      wx.shareFileMessage({filePath:this.data.exportPath,fileName:this.data.exportName,
        fail:err=>{if(!/cancel/.test(err.errMsg || '')) toast('转发未完成，请重试');}});
      return;
    }
    if(this.data.exportState === 'downloading' || this.data.transcript.status !== 'completed') return;
    this.setData({exportState:'downloading'});
    api.transcriptExport(this.data.cardId,'txt').then(({url,header})=>{
      this._exportTask=wx.downloadFile({url,header,
        success:res=>{
          if(res.statusCode !== 200) {this.setData({exportState:'idle'});return toast('导出未完成，请重试');}
          const filename=(this.data.title || '视频文案').replace(/[\\/:*?"<>|]/g,'_').slice(0,45)+'_'+this.data.cardId+'.txt';
          const dest=wx.env.USER_DATA_PATH+'/'+filename;
          wx.getFileSystemManager().copyFile({srcPath:res.tempFilePath,destPath:dest,
            success:()=>{this.setData({exportState:'ready',exportPath:dest,exportName:filename});toast('已下载，请点击转发到微信');},
            fail:()=>{this.setData({exportState:'idle'});toast('存储空间不足，请清理后重试');}});
        },
        fail:()=>{this.setData({exportState:'idle'});toast('导出未完成，请重试');}
      });
    }).catch(err=>{this.setData({exportState:'idle'});toast(err.message || '导出未完成');});
  }
});
