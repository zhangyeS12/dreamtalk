export function startSettingsBridge(): Promise<{
  world: string;
  requests: Request[];
  fetcher: typeof fetch;
  close: () => Promise<void>;
}>;
export function syntheticCardFile(document: unknown): File;
