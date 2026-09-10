const root = ["api", "platform"] as const;
function resourceKeys(name: string) {
  const all = [...root, name] as const;
  return {
    all,
    list: () => [...all, "list"] as const,
    detail: (id: string) => [...all, "detail", id] as const,
  };
}
export const queryKeys = {
  platform: {
    all: root,
    workflowPackages: {
      ...resourceKeys("workflowPackages"),
      preparation: (input: object) =>
        [...root, "workflowPackages", "preparation", input] as const,
    },
    runs: {
      ...resourceKeys("runs"),
      history: (query: object) => [...root, "runs", "list", query] as const,
      metadata: (id: string) => [...root, "runs", "detail", id, "metadata"] as const,
      result: (id: string) =>
        [...root, "runs", "detail", id, "result"] as const,
      reuse: (id: string) => [...root, "runs", "detail", id, "reuse"] as const,
    },
    taskPresets: resourceKeys("taskPresets"),
    taskDrafts: resourceKeys("taskDrafts"),
    modelUsage: {
      all: [...root, "modelUsage"] as const,
      run: (id: string) => [...root, "modelUsage", "run", id] as const,
      day: (date: string, timezone: string) => [...root, "modelUsage", "day", date, timezone] as const,
    },
    attention: {
      all: [...root, "attention"] as const,
      list: (query: object) => [...root, "attention", "list", query] as const,
    },
    schedules: {
      ...resourceKeys("schedules"),
      fires: (id: string) => [...root, "schedules", "fires", id] as const,
      preview: (id: string, revision?: number) =>
        [...root, "schedules", "detail", id, "preview", revision] as const,
    },
    resources: {
      ...resourceKeys("resources"),
      connectionPresets: () =>
        [...root, "resources", "connectionPresets"] as const,
    },
    plugins: resourceKeys("plugins"),
    artifacts: resourceKeys("artifacts"),
  },
};
