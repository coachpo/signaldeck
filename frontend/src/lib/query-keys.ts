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
    workflowPackages: resourceKeys("workflowPackages"),
    runs: resourceKeys("runs"),
    schedules: {
      ...resourceKeys("schedules"),
      fires: (id: string) => [...root, "schedules", "fires", id] as const,
    },
    resources: resourceKeys("resources"),
    plugins: resourceKeys("plugins"),
    artifacts: resourceKeys("artifacts"),
  },
};
