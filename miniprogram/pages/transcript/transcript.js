const api = require('../../utils/api');
const transcriptClient = require('../../utils/transcript');
const {formatDuration} = require('../../utils/format');
function toast(title) { wx.showToast({title,icon:'none'}); }
function decode(value) { try {return decodeURIComponent(value || '');} catch(e) {return '';} }
Page({
  data: {cardId:0,title:'',author:'',durationText:'',languageText:'',tab:'timeline',lines:[],plainText:'',
    transcript:transcriptClient.decorate(),transcriptReadError:'',exportState:'idle',exportPath:'',exportName:''},
  onLoad(options) {
    const id=Number(options.id);
    this.setData({cardId:Number.isInteger(id) && id>0 ? id:0,title:decode(options.title),author:decode(options.author),
      durationText:formatDuration(Number(options.duration)||0)});
    if(!this.data.cardId) toast('视频信息无效，请返回重试');
  },
  onShow() {this._transcriptVisible=true;transcriptClient.refresh(this);},
  onHide() {transcriptClient.stop(this);},
  onUnload() {transcriptClient.stop(this);if(this._exportTask) this._exportTask.abort();},
  onTranscriptUpdate(value) {
    const lines=(value.segments || []).map(s => Object.assign({},s,{timeText:formatDuration(s.start)}));
    this.setData({lines,plainText:lines.map(s => s.text).join('\n'),languageText:value.language === 'zh' ? '中文':(value.language || '')});
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
