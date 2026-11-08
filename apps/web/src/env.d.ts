declare module "virtual:core-connection" {
  import type { CoreConnection } from "@dreamtalk/api-client";
  const connection: CoreConnection | null;
  export default connection;
}
