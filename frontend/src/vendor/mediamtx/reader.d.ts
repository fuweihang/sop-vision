/** MediaMTX v1.20.1 reader.js 暴露的公开构造参数。 */
interface MediaMTXWebRTCReaderConfiguration {
  url: string;
  user?: string;
  pass?: string;
  token?: string;
  onError?: (error: string) => void;
  onTrack?: (event: RTCTrackEvent) => void;
  onDataChannel?: (event: RTCDataChannelEvent) => void;
}

/**
 * 官方 reader 只公开构造函数和 close()；项目代码不得通过声明文件虚构私有 PeerConnection 等能力。
 */
interface MediaMTXWebRTCReaderInstance {
  close(): void;
}

interface MediaMTXWebRTCReaderConstructor {
  new (
    configuration: MediaMTXWebRTCReaderConfiguration,
  ): MediaMTXWebRTCReaderInstance;
}

interface Window {
  MediaMTXWebRTCReader: MediaMTXWebRTCReaderConstructor;
}
