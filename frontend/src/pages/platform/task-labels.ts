/** Resource names come from the saved resource or plugin contract. */
export function connectionName(name: string, id: string) {
  return name || id;
}
