/** Display saved names without promoting internal identities into visible labels. */
export function connectionName(name: string, id: string) {
  return name.trim() && name !== id ? name : "服务连接";
}
