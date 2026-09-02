/** React Hook Form 的错误消息类型较宽；UI 只显示经过验证的文本。 */
export function fieldErrorMessage(message: unknown) {
  return typeof message === "string" ? message : undefined;
}
