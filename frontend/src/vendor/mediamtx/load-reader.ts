import "@/vendor/mediamtx/reader.js";

/**
 * `reader.js` 是声明全局构造函数的官方脚本，不是 ES module。项目代码动态 import 这个包装模块，
 * 既能让 Vite 生成独立 chunk，也无需修改受 SHA-256 校验保护的上游文件。
 */
export {};
