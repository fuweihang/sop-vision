/** total 为零时没有可导航页；其他情况按 API 返回的 page_size 向上取整。 */
export function cameraPageCount(total: number, pageSize: number) {
  return total === 0 ? 0 : Math.ceil(total / pageSize);
}
